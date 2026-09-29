"""Inventory changed files and conservative operational import reachability.

This is a read-only source audit, not proof that a branch ran. It never loads
advertisements, predictions, credentials, or evaluation answers.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path


ENTRYPOINTS = (
    "scripts/serve-operational-review.py",
    "scripts/serve_loopback_proxy.py",
    "scripts/operational_web_bridge.py",
    "rag-pipeline/rag/api/service.py",
    "rag-pipeline/tools/run_operational_e2e.py",
    "rag-pipeline/tools/run_gemma_exhaustive_dgx.py",
)


def cli_contract(caller: str, runner: str, runner_name: str) -> dict:
    """Compare literal argv options with the target's argparse declarations.

    Computed options and argument values require separate execution tests.
    A script-name literal only identifies a command builder, not execution.
    """
    target = ast.parse(runner)
    supported = {
        arg.value for node in ast.walk(target)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for arg in node.args if isinstance(arg, ast.Constant)
        and isinstance(arg.value, str) and arg.value.startswith("--")
    }
    passed = set()
    builders = []
    for function in ast.walk(ast.parse(caller)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(n, ast.Constant) and n.value == runner_name
                       for n in ast.walk(node.value)):
                continue
            variables = {n.id for n in node.targets if isinstance(n, ast.Name)}
            values = [node.value]
            for call in ast.walk(function):
                if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id in variables
                        and call.func.attr in {"append", "extend"}):
                    values.extend(call.args)
            builders.append(function.name)
            passed.update(n.value for value in values for n in ast.walk(value)
                          if isinstance(n, ast.Constant) and isinstance(n.value, str)
                          and n.value.startswith("--"))
    return {"builders": sorted(set(builders)), "passed": sorted(passed),
            "unsupported": sorted(passed - supported),
            "status": "UNSUPPORTED_OPTIONS" if passed - supported else
                      "STATIC_OPTIONS_MATCH" if builders else "CALLER_NOT_FOUND",
            "runtime_execution_verified": False}


def audit(root: Path, base: str, deployed: dict[str, str]) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "safe.directory=" + root.as_posix(), *args],
            cwd=root, encoding="utf-8")

    changed = git("diff", "--name-only", base, "HEAD").splitlines()
    tracked = git("ls-files", "*.py").splitlines()
    modules = defaultdict(set)
    trees = {}
    for name in tracked:
        path = root / name
        if not path.is_file():
            continue
        trees[name] = ast.parse(path.read_text(encoding="utf-8-sig"))
        modules[path.stem].add(name)
        for prefix in ("rag-pipeline/", "apps/backend/src/", "scripts/"):
            if name.startswith(prefix):
                module = name[len(prefix):-3].replace("/", ".")
                modules[module.removesuffix(".__init__")].add(name)
    edges = defaultdict(set)
    referenced_by = defaultdict(set)
    for name, tree in trees.items():
        for node in ast.walk(tree):
            imports = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for module in imports:
                for target in modules.get(module, ()):
                    edges[name].add(target)
                    referenced_by[target].add(name)
            # Subprocess and importlib script references are conservative edges.
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py"):
                for target in modules.get(Path(node.value).stem, ()):
                    edges[name].add(target)
                    referenced_by[target].add(name)
    reached = set(ENTRYPOINTS)
    queue = list(ENTRYPOINTS)
    while queue:
        for target in edges[queue.pop()] - reached:
            if "/tests/" not in target and not target.startswith("tests/"):
                reached.add(target)
                queue.append(target)
    rows = []
    for name in changed:
        path = root / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        rows.append({
            "path": name, "sha256": digest,
            "source_reachable_from_operational_entry": name in reached if name in trees else None,
            "referenced_by": sorted(referenced_by[name]),
            "deployment": "MATCH" if name in deployed and digest == deployed[name] else
                          "DIFFERENT" if name in deployed else "NOT_COMPARED",
            "semantic_review": "NOT_CERTIFIED_BY_STATIC_AUDIT",
        })
    contract = cli_contract(
        (root / "rag-pipeline/rag/api/service.py").read_text(encoding="utf-8"),
        (root / "rag-pipeline/tools/run_operational_e2e.py").read_text(encoding="utf-8"),
        "run_operational_e2e.py")
    return {"schema_version": "runtime-lifecycle-audit-v1", "base": base,
            "head": git("rev-parse", "HEAD").strip(), "entrypoints": ENTRYPOINTS,
            "scope": "base-to-HEAD file set; hashes and AST use current working files",
            "limits": "Static reachability includes inactive branches; deployment match is not execution proof.",
            "cli_contract": contract, "files": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--deployed-hashes", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    deployed = json.loads(args.deployed_hashes.read_text(encoding="utf-8-sig")) if args.deployed_hashes else {}
    report = audit(root, args.base, deployed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(report["files"]), "cli_contract": report["cli_contract"]}, ensure_ascii=False))
    return 1 if report["cli_contract"]["status"] != "STATIC_OPTIONS_MATCH" else 0


if __name__ == "__main__":
    raise SystemExit(main())
