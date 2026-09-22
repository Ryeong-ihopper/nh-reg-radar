# -*- coding: utf-8 -*-
"""DGX Spark GPU에서 BGE-M3 임베딩과 선택적 리랭킹을 제공한다.

외부 패키지로 웹 프레임워크를 추가하지 않고 표준 라이브러리 HTTP 서버를 쓴다.
임베딩 모델은 시작할 때 GPU에 올리고, 리랭커는 실제 요청이 있을 때만 올린다.
"""
from __future__ import annotations

import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import numpy as np
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer


HOST = os.environ.get("BGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("BGE_PORT", "8103"))
EMBED_MODEL = os.environ.get("BGE_EMBED_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.environ.get("BGE_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
MAX_TEXTS = int(os.environ.get("BGE_MAX_TEXTS", "10000"))


if not torch.cuda.is_available():
    raise RuntimeError("CUDA를 사용할 수 없어 BGE GPU 서비스를 시작하지 않음")

_embed_lock = threading.Lock()
_rerank_lock = threading.Lock()
_reranker: CrossEncoder | None = None

embedder = SentenceTransformer(
    EMBED_MODEL,
    device="cuda",
    local_files_only=True,
    model_kwargs={"torch_dtype": torch.float16},
)
embedder.max_seq_length = 1024


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON 객체가 필요함")
    return payload


def _texts(payload: dict[str, Any]) -> list[str]:
    texts = payload.get("texts")
    if not isinstance(texts, list) or not texts or len(texts) > MAX_TEXTS:
        raise ValueError(f"texts는 1..{MAX_TEXTS}개 문자열 배열이어야 함")
    if any(not isinstance(text, str) for text in texts):
        raise ValueError("texts의 모든 원소는 문자열이어야 함")
    return texts


class Handler(BaseHTTPRequestHandler):
    server_version = "cg-bge-gpu/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def _json(self, status: int, value: dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json(404, {"error": "not found"})
            return
        self._json(200, {
            "status": "ok",
            "device": "cuda",
            "gpu": torch.cuda.get_device_name(0),
            "embedding_model": EMBED_MODEL,
            "embedding_dimension": embedder.get_sentence_embedding_dimension(),
            "max_seq_length": embedder.max_seq_length,
            "reranker_loaded": _reranker is not None,
        })

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = _read_json(self)
            if self.path == "/embed":
                self._embed(payload)
            elif self.path == "/rerank":
                self._rerank(payload)
            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    def _embed(self, payload: dict[str, Any]) -> None:
        texts = _texts(payload)
        batch_size = int(payload.get("batch_size", 64))
        with _embed_lock:
            vectors = embedder.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=bool(payload.get("normalize_embeddings", True)),
                show_progress_bar=False,
            ).astype("float32")
        buffer = io.BytesIO()
        np.save(buffer, vectors, allow_pickle=False)
        raw = buffer.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-npy")
        self.send_header("X-Model", EMBED_MODEL)
        self.send_header("X-Device", "cuda")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _rerank(self, payload: dict[str, Any]) -> None:
        pairs = payload.get("pairs")
        if not isinstance(pairs, list) or not pairs or len(pairs) > MAX_TEXTS:
            raise ValueError(f"pairs는 1..{MAX_TEXTS}개 배열이어야 함")
        if any(not isinstance(pair, list) or len(pair) != 2 for pair in pairs):
            raise ValueError("각 pair는 [query, document]여야 함")
        global _reranker
        with _rerank_lock:
            if _reranker is None:
                _reranker = CrossEncoder(
                    RERANK_MODEL,
                    device="cuda",
                    max_length=int(payload.get("max_length", 512)),
                    local_files_only=True,
                    model_kwargs={"torch_dtype": torch.float16},
                )
            scores = _reranker.predict(
                pairs,
                batch_size=int(payload.get("batch_size", 16)),
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        self._json(200, {
            "model": RERANK_MODEL,
            "device": "cuda",
            "scores": np.asarray(scores, dtype="float32").tolist(),
        })


if __name__ == "__main__":
    print(json.dumps({
        "status": "starting",
        "host": HOST,
        "port": PORT,
        "device": "cuda",
        "gpu": torch.cuda.get_device_name(0),
        "embedding_model": EMBED_MODEL,
    }, ensure_ascii=False), flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
