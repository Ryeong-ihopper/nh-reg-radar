from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

Scope = Literal["all", "staged", "working", "diff"]


class GitCommandError(RuntimeError):
    pass


def _run_git(root: Path, arguments: Sequence[str]) -> tuple[int, str, str]:
    process = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def find_repository_root(start: Path) -> Path:
    code, output, _ = _run_git(start, ("rev-parse", "--show-toplevel"))
    return Path(output).resolve() if code == 0 and output else start.resolve()


def _names(root: Path, arguments: Sequence[str]) -> set[str]:
    code, output, error = _run_git(root, arguments)
    if code != 0:
        command = " ".join(arguments)
        detail = error or "unknown git error"
        raise GitCommandError(f"git {command} failed: {detail}")
    if not output:
        return set()
    return set(output.splitlines())


def changed_files(root: Path, scope: Scope, base_ref: str | None) -> list[str]:
    if scope == "all":
        return []
    if scope == "staged":
        paths = _names(root, ("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    elif scope == "working":
        paths = _names(root, ("diff", "--name-only", "--diff-filter=ACMR"))
        paths.update(
            _names(
                root,
                ("diff", "--cached", "--name-only", "--diff-filter=ACMR"),
            )
        )
        paths.update(_names(root, ("ls-files", "--others", "--exclude-standard")))
    elif scope == "diff":
        reference = base_ref or "HEAD~1"
        paths = _names(
            root,
            ("diff", "--name-only", "--diff-filter=ACMR", f"{reference}...HEAD"),
        )
    return sorted(paths)
