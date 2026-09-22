"""Build a no-model-call prompt ablation and split-readiness artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.evaluation.prompt_ablation import build_protocol


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--batches", type=Path, required=True)
    parser.add_argument("--legacy-dev-score", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = build_protocol(
        json.loads(args.plans.read_text(encoding="utf-8")),
        json.loads(args.batches.read_text(encoding="utf-8")),
        json.loads(args.legacy_dev_score.read_text(encoding="utf-8")) if args.legacy_dev_score else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(protocol["execution_state"], ensure_ascii=False))


if __name__ == "__main__":
    main()
