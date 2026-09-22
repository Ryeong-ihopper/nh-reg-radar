"""Build a private, hashed source bundle without credentials or runtime data."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache",
            "visual-artifacts", "playwright-report", "test-results"}


def files(root: Path):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (path.is_symlink() or EXCLUDED.intersection(relative.parts)
                or path.name.startswith(".env") or path.suffix in {".pyc", ".pyo", ".tsbuildinfo"}):
            continue
        if path.is_file():
            yield path, relative


def package(output: Path, parser_root: Path, document_processor_root: Path):
    sources = []
    for folder in ("apps/frontend", "apps/backend/src", "packages/ai-providers/src",
                   "packages/parser-contracts/src", "rag-pipeline/rag", "rag-pipeline/tools",
                   "rag-pipeline/schemas", "scripts", "infra/operational"):
        sources.extend((p, Path(folder) / r) for p, r in files(ROOT / folder))
    sources.append((ROOT / "rag-pipeline/requirements-rag.txt", Path("rag-pipeline/requirements-rag.txt")))
    parser_fin = (parser_root / "run.py").is_file() and (
        parser_root / "nh_parser_fin/__init__.py"
    ).is_file() and (parser_root / "pyproject.toml").is_file()
    if not parser_fin:
        raise ValueError("nh-parser-fin run.py, pyproject.toml and package source are required")
    sources.extend((p, Path("private/nh-parser") / r) for p, r in files(parser_root))
    sources.extend((p, Path("private/document-processor/src") / r)
                   for p, r in files(document_processor_root / "src"))
    if not (document_processor_root / "src/document_processor/__init__.py").is_file():
        raise ValueError("private document-processor source is required")
    manifest = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path, target in sources:
            body = path.read_bytes()
            name = target.as_posix()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(body), 0o644
            archive.addfile(info, io.BytesIO(body))
            manifest[name] = hashlib.sha256(body).hexdigest()
        body = json.dumps({"schema": "nh-operational-source-bundle-v1", "sha256": manifest},
                          ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo("source-manifest.json")
        info.size, info.mode = len(body), 0o644
        archive.addfile(info, io.BytesIO(body))
    return {"files": len(manifest), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser-root", type=Path, required=True)
    parser.add_argument("--document-processor-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output, args.parser_root, args.document_processor_root)))
