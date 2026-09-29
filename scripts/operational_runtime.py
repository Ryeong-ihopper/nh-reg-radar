"""Validate and stage the explicitly reviewed operational application files."""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "infra/operational/runtime-files.json"
SOURCE_ROOTS = (
    "apps/backend/src", "packages/ai-providers/src",
    "packages/parser-contracts/src", "rag-pipeline/rag",
    "rag-pipeline/tools", "scripts",
)
IMPORT_ROOTS = (
    "apps/backend/src/", "packages/ai-providers/src/",
    "packages/parser-contracts/src/", "rag-pipeline/", "scripts/",
)


def runtime_files(root: Path = ROOT) -> list[tuple[Path, str]]:
    root = root.resolve()
    document = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if document.get("schema") != "nh-operational-runtime-files-v1":
        raise ValueError("unsupported runtime file manifest")
    names = document["files"]
    if not isinstance(names, list) or not names or any(not isinstance(n, str) for n in names):
        raise ValueError("runtime files must be a nonempty string list")
    if len(names) != len(set(names)):
        raise ValueError("duplicate runtime file")
    sources = []
    for name in names:
        relative = PurePosixPath(name)
        if (relative.is_absolute() or relative.as_posix() != name or "\\" in name
                or ":" in name or ".." in relative.parts):
            raise ValueError(f"unsafe runtime path: {name}")
        path = root / name
        if any((root.joinpath(*relative.parts[:i])).is_symlink()
               for i in range(1, len(relative.parts) + 1)):
            raise ValueError(f"symlink runtime path: {name}")
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError(f"missing runtime file: {name}")
        sources.append((path, name))
    if not set(document["entrypoints"]).issubset(names):
        raise ValueError("missing runtime entrypoint")
    _validate_dependencies(root, {name for _, name in sources})
    return sources


def _validate_dependencies(root: Path, included: set[str]) -> None:
    """Catch repository imports and literal subprocess/hash paths omitted by edits.

    This is a conservative build guard, not proof of dynamic path coverage.
    Isolated import/CLI tests complement it; offline tools are not deleted.
    """
    modules: dict[str, set[str]] = defaultdict(set)
    basenames: dict[str, set[str]] = defaultdict(set)
    own_modules = {}
    for folder in SOURCE_ROOTS:
        for path in (root / folder).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            name = path.relative_to(root).as_posix()
            prefix = next(p for p in IMPORT_ROOTS if name.startswith(p))
            module = name[len(prefix):-3].replace("/", ".").removesuffix(".__init__")
            modules[module].add(name)
            modules[path.stem].add(name)
            own_modules[name] = module
            basenames[path.name].add(name)
    for name in sorted(included):
        if not name.endswith(".py"):
            continue
        required: set[str] = set()

        def require_module(module: str) -> None:
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                required.update(modules.get(".".join(parts[:length]), ()))

        for node in ast.walk(ast.parse((root / name).read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    require_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    own = own_modules[name].split(".")
                    package = own if name.endswith("/__init__.py") else own[:-1]
                    module = ".".join(package[:len(package) - node.level + 1]
                                      + ([module] if module else []))
                require_module(module)
                for alias in node.names:
                    require_module(module + "." + alias.name)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.endswith(".py"):
                    required.update(basenames.get(PurePosixPath(node.value).name, ()))
        missing = required - included
        if missing:
            raise ValueError(f"omitted runtime dependencies in {name}: {sorted(missing)}")


def stage(output: Path, root: Path = ROOT) -> dict:
    sources = runtime_files(root)
    output = output.resolve()
    if output == root.resolve() or output in root.resolve().parents:
        raise ValueError("runtime output must be a separate empty directory")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("runtime output must be a separate empty directory")
    hashes = {}
    for source, name in sources:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt = {"schema": "nh-operational-runtime-snapshot-v1", "sha256": hashes}
    (output / "runtime-files-manifest.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"files": len(stage(args.output)["sha256"])}))
