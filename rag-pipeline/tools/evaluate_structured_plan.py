"""Replay one local plan with verified facts; no model call or persisted review mutation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.judgment.structured_predicates import evaluate_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.review.read_text(encoding="utf-8"))
    matches = [p for p in document["plans"] if p["plan_id"] == args.plan]
    if len(matches) != 1:
        raise ValueError("plan must resolve exactly once")
    result = evaluate_plan(matches[0], json.loads(args.facts.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["verdict"])


if __name__ == "__main__":
    main()
