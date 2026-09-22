"""Build the pre-runtime structured methodology artifact from lossless extracts."""
from __future__ import annotations

import argparse
from pathlib import Path

from rag.templates.structured_methodology import write_compiled_methodologies


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = write_compiled_methodologies(args.extract_root, args.output)
    counts = document["counts"]
    print(
        f"structured {counts['methodology_rules']} methodology rows, "
        f"{counts['shared_rules']} shared rule, {counts['scope_policies']} scope policy"
    )


if __name__ == "__main__":
    main()
