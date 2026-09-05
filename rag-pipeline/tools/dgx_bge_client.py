# -*- coding: utf-8 -*-
"""로컬 파이프라인에서 DGX Spark의 BGE GPU 서비스를 호출한다."""
from __future__ import annotations

import io
import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

import numpy as np


DEFAULT_HOST = os.environ.get("DGX_HOST")
DEFAULT_KEY = Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None
ENDPOINT = os.environ.get("DGX_BGE_ENDPOINT", "http://127.0.0.1:8103")
LOCAL_ENDPOINT = os.environ.get("DGX_BGE_LOCAL_ENDPOINT", "http://127.0.0.1:8103")


def _remote_post(path: str, *, binary: bool) -> str:
    writer = "sys.stdout.buffer.write(raw)" if binary else "sys.stdout.buffer.write(raw)"
    return (
        "import sys,urllib.request;"
        "data=sys.stdin.buffer.read();"
        f"req=urllib.request.Request('{ENDPOINT}{path}',data=data,headers={{'Content-Type':'application/json'}});"
        "raw=urllib.request.urlopen(req,timeout=1800).read();"
        f"{writer}"
    )


def _call(path: str, payload: dict, *, host: str | None, key: Path | None) -> bytes:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{LOCAL_ENDPOINT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        # 터널이 없을 때도 CPU로 후퇴하지 않는다. SSH를 통해 같은 DGX GPU
        # 서비스에 접속한다. 운영에서는 8103 터널을 유지해 호출당 SSH 비용을 없앤다.
        pass
    if not host or key is None:
        raise RuntimeError(
            "local BGE endpoint is unavailable; set DGX_HOST and DGX_SSH_KEY for SSH fallback"
        )
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-i", str(key), host, "python3", "-c", shlex.quote(_remote_post(path, binary=True)),
    ]
    process = subprocess.run(
        command,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1860,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace"))
    return process.stdout


def health(*, host: str | None = DEFAULT_HOST, key: Path | None = DEFAULT_KEY) -> dict:
    try:
        with urllib.request.urlopen(f"{LOCAL_ENDPOINT}/health", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        pass
    if not host or key is None:
        raise RuntimeError(
            "local BGE endpoint is unavailable; set DGX_HOST and DGX_SSH_KEY for SSH fallback"
        )
    remote = (
        "import sys,urllib.request;"
        f"sys.stdout.buffer.write(urllib.request.urlopen('{ENDPOINT}/health',timeout=30).read())"
    )
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-i", str(key), host, "python3", "-c", shlex.quote(remote),
    ]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace"))
    return json.loads(process.stdout.decode("utf-8"))


def encode(
    texts: Sequence[str],
    *,
    batch_size: int = 64,
    host: str | None = DEFAULT_HOST,
    key: Path | None = DEFAULT_KEY,
) -> np.ndarray:
    if not texts:
        return np.empty((0, 1024), dtype="float32")
    raw = _call("/embed", {
        "texts": list(texts),
        "batch_size": batch_size,
        "normalize_embeddings": True,
    }, host=host, key=key)
    matrix = np.load(io.BytesIO(raw), allow_pickle=False).astype("float32")
    if matrix.ndim != 2 or matrix.shape[0] != len(texts):
        raise RuntimeError(f"DGX 임베딩 shape 불일치: {matrix.shape}, texts={len(texts)}")
    return matrix


class DGXSentenceEncoder:
    """SentenceTransformer의 ``encode`` 최소 인터페이스를 원격 GPU로 대체한다."""

    max_seq_length = 1024

    def __init__(
        self,
        *,
        host: str | None = DEFAULT_HOST,
        key: Path | None = DEFAULT_KEY,
        default_batch_size: int = 64,
    ) -> None:
        self.host = host
        self.key = key
        self.default_batch_size = default_batch_size
        service = health(host=host, key=key)
        if service.get("device") != "cuda" or service.get("embedding_model") != "BAAI/bge-m3":
            raise RuntimeError(f"DGX BGE 서비스 계약 불일치: {service}")

    def encode(
        self,
        texts: Sequence[str],
        *,
        batch_size: int | None = None,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        **_: Any,
    ) -> np.ndarray:
        if not convert_to_numpy:
            raise ValueError("DGXSentenceEncoder는 numpy 출력만 지원함")
        if not normalize_embeddings:
            raise ValueError("현행 BGE 계약은 정규화 임베딩만 지원함")
        return encode(
            texts,
            batch_size=batch_size or self.default_batch_size,
            host=self.host,
            key=self.key,
        )


def rerank(
    pairs: Sequence[Sequence[str]],
    *,
    batch_size: int = 16,
    max_length: int = 512,
    host: str | None = DEFAULT_HOST,
    key: Path | None = DEFAULT_KEY,
) -> np.ndarray:
    if not pairs:
        return np.empty((0,), dtype="float32")
    raw = _call("/rerank", {
        "pairs": [list(pair) for pair in pairs],
        "batch_size": batch_size,
        "max_length": max_length,
    }, host=host, key=key)
    result = json.loads(raw.decode("utf-8"))
    scores = np.asarray(result["scores"], dtype="float32")
    if scores.shape != (len(pairs),):
        raise RuntimeError(f"DGX 리랭커 shape 불일치: {scores.shape}, pairs={len(pairs)}")
    return scores
