"""Compile the 305-item template/supplemental routing audit from local extracts."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.judgment.execution_routing import build_complete_routing  # noqa: E402


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _responsibility_rows(path: Path) -> list[dict[str, object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    values = list(workbook.worksheets[0].values)
    headers = values[0]
    rows = [dict(zip(headers, values, strict=True)) for values in values[1:]]
    return [row for row in rows if row["업권 재검토 상태"] == "대상 템플릿 관련 후보 유지"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-items", type=Path, required=True)
    parser.add_argument("--responsibilities", type=Path, required=True)
    parser.add_argument("--activation-policy", type=Path, required=True)
    parser.add_argument("--structured-methodology", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    methodology = json.loads(args.structured_methodology.read_text(encoding="utf-8"))
    loan = [row for row in methodology["rules"] if row["template_section"] == "대출성상품-상품명 노출"]
    policy = json.loads(args.activation_policy.read_text(encoding="utf-8"))
    document = build_complete_routing(
        _csv_rows(args.template_items),
        _responsibility_rows(args.responsibilities),
        policy["entries"],
        loan,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
