"""Keep the reviewed functional package boundary from drifting back to vague folders."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_has_no_shadowed_top_level_definitions() -> None:
    duplicates = []
    for path in [*ROOT.joinpath("rag").rglob("*.py"), *ROOT.joinpath("tools").glob("*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in names:
                    duplicates.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")
                names.add(node.name)
    assert not duplicates, duplicates


def test_function_packages_exist_and_obsolete_operational_package_is_absent() -> None:
    for name in ("contracts", "parsing", "templates", "judgment", "api"):
        assert (ROOT / "rag" / name / "__init__.py").is_file()
    assert not (ROOT / "rag" / "operational").exists()


def test_runtime_does_not_import_legacy_package() -> None:
    runtime_files = [
        *ROOT.joinpath("rag").rglob("*.py"),
        *ROOT.joinpath("tools").glob("*.py"),
    ]
    import_legacy = re.compile(r"^(?:from|import)\s+(?:rag_pipeline\.)?legacy\b", re.MULTILINE)
    leaked = [
        str(path.relative_to(ROOT))
        for path in runtime_files
        if import_legacy.search(path.read_text(encoding="utf-8"))
    ]
    assert not leaked
