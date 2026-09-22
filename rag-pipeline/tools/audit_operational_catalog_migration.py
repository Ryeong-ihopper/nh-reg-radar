"""Write an exact legacy-ID migration audit for canonical execution plans."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.templates.operational_catalog_migration import audit_catalog_migration


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--legacy-catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    plans = json.loads(args.plans.read_text(encoding="utf-8"))["plans"]
    legacy = json.loads(args.legacy_catalog.read_text(encoding="utf-8"))
    report = audit_catalog_migration(plans, legacy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
