"""Export one review row per atomic obligation."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--migration", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    if args.csv.exists() or args.summary.exists():
        raise ValueError("output already exists")
    document = json.loads(args.plans.read_text(encoding="utf-8"))
    migration = json.loads(args.migration.read_text(encoding="utf-8"))
    migration_by_id = {row["plan_id"]: row for row in migration["rows"]}
    rows = [_review_row(plan, atom, migration_by_id[plan["plan_id"]])
            for plan in document["plans"] for atom in plan["obligations"]]
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.summary.write_text(_summary(document, migration, rows), encoding="utf-8")
    print(json.dumps({"plans": len(document["plans"]), "obligations": len(rows),
                      "csv": str(args.csv), "summary": str(args.summary)}, ensure_ascii=False))


def _review_row(plan: dict[str, Any], atom: dict[str, Any], migration: dict[str, Any]) -> dict[str, str]:
    source = plan["source"]
    owners = [name.upper() for name, enabled in atom["owners"].items() if enabled]
    return {
        "plan_id": plan["plan_id"],
        "obligation_id": atom["obligation_id"],
        "source_kind": source["source_kind"],
        "product_template": str(source.get("product_template") or ""),
        "label": str(source.get("label") or ""),
        "prompt_family": plan["prompt_family"],
        "applicability_inputs": json.dumps(plan["applicability_inputs"], ensure_ascii=False),
        "applicability_logic": json.dumps(plan["applicability_logic"], ensure_ascii=False),
        "obligation": atom["text"],
        "owners": "+".join(owners),
        "external_input_required": str(atom["owners"]["external_input"]),
        "human_review_required": str(atom["owners"]["human"]),
        "interpretation_hints": json.dumps(atom["interpretation_hints"], ensure_ascii=False),
        "retrieval_queries": json.dumps(atom["retrieval_queries"], ensure_ascii=False),
        "obligation_logic": json.dumps(plan["obligation_logic"], ensure_ascii=False),
        "held_facets": json.dumps(plan["held_facets"], ensure_ascii=False),
        "migration_state": migration["migration_state"],
        "legacy_item_ids": ",".join(migration["legacy_item_ids"]),
        "source_sha256": plan["source_sha256"],
    }


def _summary(document: dict[str, Any], migration: dict[str, Any], rows: list[dict[str, str]]) -> str:
    owners = Counter(row["owners"] for row in rows)
    families = document["counts"]["families"]
    lines = [
        "# 예금·대출·투자 실행계획 검토 요약",
        "",
        "이 문서는 규칙 생성 입력만 집계한다. 광고 답지·예측·피드백은 읽지 않았다.",
        "",
        f"- 후보 원본 행: {document['counts']['candidate_source_records']}개",
        f"- 원자 의무: {document['counts']['obligation_atoms']}개",
        f"- 적용조건 입력: {document['counts']['application_inputs']}개",
        f"- 미해결 전체 규칙: {document['counts']['plans_with_unresolved']}개",
        f"- 출처 충돌로 일부 조건만 보류한 규칙: {document['counts']['plans_with_held_facets']}개",
        f"- 기존 운영 ID 정확 매핑: {migration['counts'].get('EXACT_LEGACY_ALIAS', 0)}개",
        f"- 신규·개정 템플릿 행: {migration['counts'].get('NEW_OR_REVISED_SOURCE_ROW', 0)}개",
        f"- 추가 규칙: {migration['counts'].get('NEW_SUPPLEMENTAL_PLAN', 0)}개",
        "",
        "## 원자 의무 담당 조합",
        "",
        "| 담당 | 의무 수 |",
        "| --- | ---: |",
        *[f"| {name} | {count} |" for name, count in sorted(owners.items())],
        "",
        "## 프롬프트 규칙군",
        "",
        "| 규칙군 | 계획 수 |",
        "| --- | ---: |",
        *[f"| {name} | {count} |" for name, count in sorted(families.items())],
        "",
        "## 읽는 법",
        "",
        "CSV의 한 행은 하나의 원자 의무다. 적용조건은 코드가 계산하고, `owners`가 RULE이면 "
        "형식·수치 계산을 코드가 담당한다. LLM은 의미 동등성·오인 가능성을 관찰하며, "
        "EXTERNAL_INPUT은 같은 상품·개정본의 외부자료가 필요하다. HUMAN은 좌표·색상·배치 같은 "
        "시각 판단이다. 최종 AND/OR/NOT과 판정은 코드가 계산한다.",
        "",
        "`interpretation_hints`의 예시는 의미와 검색어를 돕는 비구속 자료이며 광고 증거가 아니다. "
        "예시가 없어도 `retrieval_queries`에는 의무와 기준 문장이 들어간다.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
