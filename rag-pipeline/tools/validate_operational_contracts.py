#!/usr/bin/env python
"""Validate canonical pipeline artifacts without reading any answer key."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.operational.contracts import (  # noqa: E402
    ContractError,
    validate_operational_result,
    validate_search_collections,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepared = subparsers.add_parser("prepared", help="validate integrated inputs and coarse/fine projections")
    prepared.add_argument("--inputs-dir", type=Path, required=True)
    prepared.add_argument("--coarse", type=Path, required=True)
    prepared.add_argument("--fine", type=Path, required=True)

    result = subparsers.add_parser("result", help="validate final operational result")
    result.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "prepared":
            inputs = [read_json(path) for path in sorted(args.inputs_dir.glob("*.json"))]
            if not inputs:
                raise ContractError(f"no integrated JSON files: {args.inputs_dir}")
            validate_search_collections(inputs, read_jsonl(args.coarse), read_jsonl(args.fine))
            print(json.dumps({"status": "PASS", "inputs": len(inputs)}, ensure_ascii=False))
        else:
            value = validate_operational_result(read_json(args.path))
            print(json.dumps({"status": "PASS", "ads": len(value["ads"])}, ensure_ascii=False))
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
