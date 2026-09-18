"""Apply the bundled template-selection compatibility patch to an explicit parser checkout."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true", help="Check compatibility without modifying files")
    args = parser.parse_args()
    root = args.parser_root.resolve()
    if not (root / "tools" / "parse.py").is_file():
        parser.error("--parser-root must contain tools/parse.py")
    patch = Path(__file__).resolve().parents[1] / "integrations/nh-ad-parser/template-id-support.patch"
    git = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), "apply"]

    def check(*options: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(git + [*options, str(patch)], capture_output=True, text=True)

    if check("--reverse", "--check").returncode == 0:
        print("Template support patch already applied; no changes.")
        return 0
    result = check("--check")
    if result.returncode:
        print("Patch conflicts with this parser checkout. No files changed.\n" + result.stderr)
        return 1
    if args.check:
        print("Patch can be applied; no files changed.")
        return 0
    result = check()
    if result.returncode:
        print(result.stderr)
        return result.returncode
    print("Template support applied. Restart the review app before retrying.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
