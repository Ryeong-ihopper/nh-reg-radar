#!/usr/bin/env python
"""Create and score leakage-resistant blind evaluation artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.evaluation.blind import (  # noqa: E402
    BlindEvaluationError,
    content_sha256,
    create_review_packet,
    evaluate_frozen_prediction,
    freeze_prediction,
    read_json,
    seal_human_labels,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("freeze")
    freeze.add_argument("--prediction", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--dataset-id", required=True)
    freeze.add_argument("--split", choices=("DEV_REGRESSION", "BLIND_HOLDOUT"), required=True)
    freeze.add_argument("--unseen-confirmed-by")
    freeze.add_argument("--unseen-confirmed-at")

    packet = commands.add_parser("packet")
    packet.add_argument("--prediction", type=Path, required=True)
    packet.add_argument("--freeze", type=Path, required=True)
    packet.add_argument("--output", type=Path, required=True)

    seal = commands.add_parser("seal")
    seal.add_argument("--packet", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument("--minimum-reviewers", type=int, default=2)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--freeze", type=Path, required=True)
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "freeze":
            prediction = read_json(args.prediction)
            value = freeze_prediction(
                prediction,
                prediction_sha256=content_sha256(prediction),
                dataset_id=args.dataset_id,
                split=args.split,
                unseen_confirmed_by=args.unseen_confirmed_by,
                unseen_confirmed_at=args.unseen_confirmed_at,
            )
        elif args.command == "packet":
            value = create_review_packet(read_json(args.prediction), read_json(args.freeze))
        elif args.command == "seal":
            value = seal_human_labels(
                read_json(args.packet), minimum_reviewers=args.minimum_reviewers
            )
        else:
            value = evaluate_frozen_prediction(
                read_json(args.freeze), read_json(args.labels)
            )
        write_json(args.output, value)
        print(json.dumps({"status": "PASS", "output": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, BlindEvaluationError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
