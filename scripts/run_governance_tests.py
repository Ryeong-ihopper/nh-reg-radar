"""Run the complete governance suite on POSIX, including from Windows via Docker.

The container receives current tracked files and nonignored local Markdown docs.
It receives neither .git credentials nor ignored settings, keys, or run artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "nh-ad-governance:py311"
TEST_COMMAND = ["-m", "unittest", "discover", "-s", "tests/governance", "-v"]
CONTAINER_RUNNER = """
import subprocess, sys, tarfile
with tarfile.open('/input/snapshot.tar') as source:
    source.extractall('/workspace', filter='data')
subprocess.run(['git', 'init', '--quiet', '/workspace'], check=True)
subprocess.run(['git', '-C', '/workspace', 'add', '.'], check=True)
sys.exit(subprocess.call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/governance', '-v'], cwd='/workspace'))
"""


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args]
    )


def write_snapshot(root: Path, destination: Path) -> int:
    """Keep working changes, Git executable modes, and locally maintained docs."""
    files: dict[str, int] = {}
    for entry in _git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, _, stage = meta.split()
        if stage != b"0":
            raise ValueError("Resolve Git conflicts before running governance tests")
        files[name.decode("utf-8")] = int(mode, 8)
    for entry in _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", "docs").split(
        b"\0"
    ):
        if entry and entry.endswith(b".md"):
            files[entry.decode("utf-8")] = 0o100644
    count = 0
    with tarfile.open(destination, "w") as archive:
        for name, mode in sorted(files.items()):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or ".git" in relative.parts:
                raise ValueError(f"Unsafe snapshot path: {name}")
            path = root / name
            if not path.exists() and not path.is_symlink():
                continue  # Preserve working-tree deletions.
            member = tarfile.TarInfo(name)
            member.mode = mode & 0o777
            if mode == 0o120000:
                member.type = tarfile.SYMTYPE
                member.linkname = (
                    os.readlink(path) if path.is_symlink() else path.read_text(encoding="utf-8")
                )
                archive.addfile(member)
            elif mode in (0o100644, 0o100755) and path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            else:
                raise ValueError(f"Unsupported snapshot entry: {name}")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--docker", action="store_true", help="Use the isolated Linux runtime on any host"
    )
    args = parser.parse_args()
    if os.name != "nt" and not cast(bool, args.docker):
        return subprocess.call([sys.executable, *TEST_COMMAND], cwd=ROOT)
    # Do not silently start the user's Docker services or skip POSIX cases.
    engine = subprocess.check_output(
        ["docker", "info", "--format", "{{.OSType}}"], text=True
    ).strip()
    if engine != "linux":
        raise ValueError("Docker Desktop must use its Linux engine for POSIX governance tests")
    _ = subprocess.run(["docker", "build", "-t", IMAGE, str(ROOT / "tests/governance")], check=True)
    with tempfile.TemporaryDirectory(prefix="nh-governance-") as temporary:
        snapshot = Path(temporary) / "snapshot.tar"
        count = write_snapshot(ROOT, snapshot)
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        print(f"Governance snapshot: files={count}, sha256={digest}; network disabled", flush=True)
        return subprocess.call(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/workspace:exec",
                "--tmpfs",
                "/tmp:exec",
                "--mount",
                f"type=bind,source={temporary},target=/input,readonly",
                "--entrypoint",
                "python3",
                IMAGE,
                "-c",
                CONTAINER_RUNNER,
            ]
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Governance runtime failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
