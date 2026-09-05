# -*- coding: utf-8 -*-
"""현행 19건 부모 근거 청크의 BGE-M3 dense 벡터를 만든다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIR = ROOT / "output" / "_rag" / "search_0902_normalized"
COARSE = SEARCH_DIR / "evidence_coarse.jsonl"
VECTORS = SEARCH_DIR / "bge_m3_coarse.f16.npy"
META = SEARCH_DIR / "bge_m3_coarse.meta.json"
MODEL_NAME = "BAAI/bge-m3"


def resolve_local_model_snapshot(model_name: str = MODEL_NAME) -> Path:
    """오프라인 캐시의 고정 snapshot 경로를 반환한다.

    repo id를 SentenceTransformer에 직접 넘기면 일부 transformers 버전은
    ``local_files_only=True``여도 선택적 processor 파일을 Hub에 조회한다.
    폐쇄망 런타임에서는 refs/main이 가리키는 로컬 snapshot을 직접 연다.
    """
    cache_root = Path(
        os.environ.get(
            "HF_HUB_CACHE",
            Path.home() / ".cache" / "huggingface" / "hub",
        )
    )
    repo_dir = cache_root / f"models--{model_name.replace('/', '--')}"
    main_ref = repo_dir / "refs" / "main"
    if not main_ref.exists():
        raise RuntimeError(f"오프라인 모델 refs/main이 없음: {main_ref}")
    revision = main_ref.read_text(encoding="utf-8").strip()
    snapshot = repo_dir / "snapshots" / revision
    required = ["config.json", "modules.json", "tokenizer.json"]
    missing = [name for name in required if not (snapshot / name).exists()]
    if missing:
        raise RuntimeError(f"오프라인 모델 snapshot 불완전: {snapshot}, missing={missing}")
    return snapshot


def read_docs(path: Path = COARSE) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corpus_key(docs: list[dict]) -> str:
    value = "\n".join(
        f"{row['doc_id']}\t{row['text_search']}" for row in docs
    ).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--device", choices=("dgx", "cuda"), default="dgx",
        help="기본값 dgx는 Spark GPU 서비스를 사용한다. CPU 후퇴는 지원하지 않는다.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--input", type=Path, default=COARSE)
    parser.add_argument("--vectors", type=Path, default=VECTORS)
    parser.add_argument("--meta", type=Path, default=META)
    args = parser.parse_args()

    docs = read_docs(args.input)
    if len({row["doc_id"] for row in docs}) != len(docs):
        raise SystemExit("중복 doc_id가 있어 벡터를 만들지 않음")
    device = args.device
    if device != "dgx":
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("--device cuda를 요청했지만 PyTorch CUDA를 사용할 수 없음")

    expected = {
        "schema_version": "ad-evidence-vector-meta-v1",
        "model": MODEL_NAME,
        "documents": len(docs),
        "source_sha256": sha256(args.input),
        "corpus_key": corpus_key(docs),
        "normalize_embeddings": True,
        "max_seq_length": 1024,
        "device": "dgx_cuda" if device == "dgx" else device,
    }
    if not args.force and args.vectors.exists() and args.meta.exists():
        meta = json.loads(args.meta.read_text(encoding="utf-8"))
        matrix = np.load(args.vectors, mmap_mode="r")
        if all(meta.get(key) == value for key, value in expected.items()) and (
            matrix.shape[0] == len(docs)
        ):
            print(json.dumps({
                "status": "valid_cache",
                "vectors": str(args.vectors),
                "documents": len(docs),
                "dimension": int(matrix.shape[1]),
            }, ensure_ascii=False, indent=2))
            return

    if device == "dgx":
        from dgx_bge_client import DGXSentenceEncoder, health

        service = health()
        if service.get("embedding_model") != MODEL_NAME or service.get("device") != "cuda":
            raise RuntimeError(f"DGX BGE 서비스 계약 불일치: {service}")
        model = DGXSentenceEncoder(default_batch_size=args.batch_size)
    else:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            str(resolve_local_model_snapshot()),
            device=device,
            local_files_only=True,
        )
        model.max_seq_length = 1024
    started = time.perf_counter()
    matrix = model.encode(
        [row["text_search"] for row in docs],
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype("float32")
    seconds = time.perf_counter() - started
    args.vectors.parent.mkdir(parents=True, exist_ok=True)
    args.meta.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.vectors, matrix.astype("float16"))
    args.meta.write_text(json.dumps({
        **expected,
        "dimension": int(matrix.shape[1]),
        "dtype": "float16",
        "device": "dgx_cuda" if device == "dgx" else device,
        "embedding_seconds": round(seconds, 3),
        "doc_ids": [row["doc_id"] for row in docs],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "created",
        "vectors": str(args.vectors),
        "meta": str(args.meta),
        "documents": len(docs),
        "dimension": int(matrix.shape[1]),
        "seconds": round(seconds, 3),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
