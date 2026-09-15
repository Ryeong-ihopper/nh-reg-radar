# -*- coding: utf-8 -*-
"""Validate that evaluation gold is bound to an exact regulation-v2 snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag import build_items as v2_source  # noqa: E402
from regulation_v2_catalog import load_template_candidate_rules  # noqa: E402


SNAPSHOT_FIELDS = ("title", "question", "criterion")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        return value["rows"]
    raise ValueError("gold must be an array or an object containing rows[]")


def validate_rows(
    rows: list[dict[str, Any]],
    item_by_id: dict[str, dict[str, Any]],
    regulation_sha256: str,
) -> list[dict[str, Any]]:
    output = []
    for index, row in enumerate(rows):
        item_id = str(row.get("item_id") or "")
        current = item_by_id.get(item_id)
        binding = row.get("regulation_binding")
        reasons: list[str] = []
        if current is None:
            status = "MISSING_RULE"
            reasons.append("item_id not found in current regulation v2")
        elif not isinstance(binding, dict):
            status = "UNBOUND"
            reasons.append("regulation_binding snapshot is absent")
        else:
            if binding.get("regulation_sha256") != regulation_sha256:
                reasons.append("regulation SHA-256 differs")
            if binding.get("item_id") != item_id:
                reasons.append("bound item_id differs")
            for field in SNAPSHOT_FIELDS:
                if binding.get(field) != current.get(field):
                    reasons.append(f"{field} differs")
            status = "BOUND" if not reasons else "DRIFT"
        output.append({
            "row_index": index,
            "ad_id": row.get("ad_id"),
            "item_id": item_id,
            "status": status,
            "reasons": reasons,
            "current_rule": None if current is None else {
                "id": current.get("id") or current.get("item_id"),
                **{field: current.get(field) for field in SNAPSHOT_FIELDS},
            },
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--regulation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    v2_source.set_agent_path(args.regulation)
    items, _ = v2_source.build()
    template_rules = load_template_candidate_rules()
    regulation_hash = sha256(args.regulation)
    item_by_id = {row["id"]: row for row in items}
    item_by_id.update({row["item_id"]: row for row in template_rules})
    results = validate_rows(load_rows(args.gold), item_by_id, regulation_hash)
    counts = Counter(row["status"] for row in results)
    payload = {
        "schema_version": "gold-v2-binding-audit-v1",
        "gold": str(args.gold.resolve()),
        "regulation": str(args.regulation.resolve()),
        "regulation_sha256": regulation_hash,
        "counts": dict(sorted(counts.items())),
        "evaluation_ready": bool(results) and counts == {"BOUND": len(results)},
        "rows": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "counts": payload["counts"],
        "evaluation_ready": payload["evaluation_ready"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
