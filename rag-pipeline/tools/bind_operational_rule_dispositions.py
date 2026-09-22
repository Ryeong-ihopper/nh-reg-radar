"""Bind the reviewed disposition registry to one canonical plan snapshot."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def bind_dispositions(plans: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    if plans.get("schema_version") != "canonical-execution-plans-v2":
        raise ValueError("expected canonical-execution-plans-v2")
    if registry.get("schema_version") != "operational-rule-dispositions-v1":
        raise ValueError("expected operational-rule-dispositions-v1")
    plan_rows = plans.get("plans") or []
    plan_ids = {str(row.get("plan_id") or "") for row in plan_rows}
    if "" in plan_ids or len(plan_ids) != len(plan_rows):
        raise ValueError("canonical plan IDs are missing or duplicated")
    active_plan_ids = {
        str(row["plan_id"])
        for row in plan_rows
        if (row.get("source") or {}).get("source_kind") != "TEMPLATE"
    }
    entries = registry.get("entries") or []
    entry_ids = {str(row.get("item_id") or "") for row in entries}
    if "" in entry_ids or len(entry_ids) != len(entries):
        raise ValueError("disposition IDs are missing or duplicated")
    registered_active = {
        str(row["item_id"]) for row in entries if row.get("state") == "ACTIVE_SUPPLEMENT"
    }
    if registered_active != active_plan_ids:
        raise ValueError("active dispositions differ from canonical supplemental plans")
    for row in entries:
        if row.get("state") == "ALIAS" and row.get("target_id") not in active_plan_ids:
            raise ValueError(f"alias target is not active: {row.get('item_id')}")
    counts = Counter(str(row.get("state") or "").lower() for row in entries)
    output = dict(registry)
    output["canonical_source_binding_sha256"] = plans["source_binding_sha256"]
    output["counts"] = dict(sorted(counts.items()))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--dispositions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    plans = json.loads(args.plans.read_text(encoding="utf-8"))
    registry = json.loads(args.dispositions.read_text(encoding="utf-8"))
    output = bind_dispositions(plans, registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "canonical_source_binding_sha256": output["canonical_source_binding_sha256"],
        "counts": output["counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
