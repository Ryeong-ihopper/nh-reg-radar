"""Read source catalogs and audit compiled checks without inference or network."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag import build_items  # noqa: E402
from rag.judgment.condition_contracts import (  # noqa: E402
    attach_condition_contracts,
    audit_compiled_rules,
    rule_view_from_v2_item,
)
from rag.templates.catalog import TemplateCatalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-hwpx", type=Path, required=True)
    parser.add_argument("--regulation", type=Path, required=True)
    parser.add_argument("--methodology-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Preserve previous audit artifacts too; a new output path is explicit.
    if args.output.exists():
        parser.error("output already exists; choose a new audit artifact")
    catalog = TemplateCatalog.from_hwpx(args.template_hwpx, methodology_dir=args.methodology_dir)
    template_rules = catalog.operational_rules()
    build_items.set_agent_path(args.regulation)
    items, _ = build_items.build()
    rules = [*template_rules, *(rule_view_from_v2_item(item) for item in items)]
    attach_condition_contracts(rules)
    report = audit_compiled_rules(rules)
    report.update(
        {
            "mode": "OFFLINE_SOURCE_AUDIT_NOT_JUDGMENT",
            "template_rule_count": len(template_rules),
            "v2_rule_count": len(items),
            "template_product_counts": dict(
                Counter(group for rule in template_rules for group in rule["product_groups"])
            ),
            "sources": [
                {"role": role, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for role, path in (
                    ("template", args.template_hwpx),
                    ("regulation", args.regulation),
                )
            ],
            "candidate_policy_changed": False,
            "predictions_generated": False,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "rules"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
