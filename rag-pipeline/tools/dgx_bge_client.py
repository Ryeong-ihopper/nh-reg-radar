# -*- coding: utf-8 -*-
"""Call BGE GPU services directly; retain the interim DGX SSH fallback."""
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

EMBEDDING_DIMENSION = 1024
MAX_SEQ_LENGTH = 1024


def validate_embeddings(matrix: np.ndarray, rows: int) -> np.ndarray:
    """Reject unusable cosine vectors before either indexing or caching them."""
    matrix = np.asarray(matrix, dtype="float32")
    if matrix.shape != (rows, EMBEDDING_DIMENSION):
        raise ValueError(f"BGE embedding shape mismatch: {matrix.shape}, rows={rows}")
    if not np.isfinite(matrix).all():
        raise ValueError("BGE embeddings contain non-finite values")
    norms = np.linalg.norm(matrix, axis=1)
    if not np.allclose(norms, 1.0, rtol=0, atol=0.01):
        raise ValueError("BGE embeddings must be nonzero unit vectors")
    return matrix


DEFAULT_HOST = os.environ.get("DGX_HOST")
DEFAULT_KEY = Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None
LOCAL_ENDPOINT = os.environ.get(
    "NH_GPU_BGE_ENDPOINT",
    os.environ.get("DGX_BGE_LOCAL_ENDPOINT", "http://127.0.0.1:8103"),
)
ENDPOINT = os.environ.get(
    "NH_GPU_BGE_REMOTE_ENDPOINT",
    os.environ.get("DGX_BGE_ENDPOINT", LOCAL_ENDPOINT),
)


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
        # CPU로 후퇴하지 않는다. 중간 DGX 프로필만 SSH fallback을 사용하며,
        # 최종 H200 프로필은 접근 가능한 내부 endpoint를 직접 주입한다.
        pass
    if not host or key is None:
        raise RuntimeError(
            "GPU BGE endpoint is unavailable; set NH_GPU_BGE_ENDPOINT or configure "
            "DGX_HOST and DGX_SSH_KEY for the interim SSH fallback"
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
            "GPU BGE endpoint is unavailable; set NH_GPU_BGE_ENDPOINT or configure "
            "DGX_HOST and DGX_SSH_KEY for the interim SSH fallback"
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
    return validate_embeddings(matrix, len(texts))


class GPUSentenceEncoder:
    """SentenceTransformer의 최소 ``encode`` 인터페이스를 GPU API로 대체한다."""

    max_seq_length = MAX_SEQ_LENGTH

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
            raise RuntimeError(f"GPU BGE 서비스 계약 불일치: {service}")
        # This client does not control server-side truncation. Verify the actual
        # service instead of recording a client property as if it were enforced.
        if (service.get("embedding_dimension") != EMBEDDING_DIMENSION
                or service.get("max_seq_length") != MAX_SEQ_LENGTH):
            raise RuntimeError("GPU BGE service must report dimension/max_seq_length=1024")

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
            raise ValueError("GPUSentenceEncoder는 numpy 출력만 지원함")
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
        raise RuntimeError(f"GPU 리랭커 shape 불일치: {scores.shape}, pairs={len(pairs)}")
    if not np.isfinite(scores).all():
        raise ValueError("GPU reranker returned non-finite scores")
    return scores


# Transitional import compatibility for existing DGX report scripts.
DGXSentenceEncoder = GPUSentenceEncoder
