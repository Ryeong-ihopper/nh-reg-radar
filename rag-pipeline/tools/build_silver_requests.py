# -*- coding: utf-8 -*-
"""규제목록 v2만으로 답지 후보 판정 입력을 만드는 공통 구현.

직접 실행하지 않고 데이터셋을 사전 등록한 래퍼에서 설정한 뒤 호출한다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from rag import build_items as v2_source  # noqa: E402
from regulation_v2_catalog import load_template_candidate_rules  # noqa: E402


CHUNKS = ROOT / "output/_rag/chunks_0831"
# A dataset wrapper must set these values explicitly.  The common builder has
# no embedded advertisement selection or historical output directory.
OUT: Path | None = None
INPUTS: Path | None = None
ADS: list[str] = []
BATCH_SIZE = 25
RUN_NAME = ""


SYSTEM = """당신은 NH 금융광고 심의 답지 초안을 만드는 검토자다.
입력에는 광고 한 건의 파싱 정본 전체와 규제목록 v2의 점검항목 묶음이 있다.
각 규칙을 독립적으로 검토하고, 입력된 rule을 단 하나도 생략하거나 추가하지 말라.

판정 원칙:
1. 광고 상품군은 제공된 routing 값을 사용한다. 파일명·파서 라벨·gubun은 규칙을 제외하는 근거로 쓰지 않는다.
2. APPLICABLE: 광고의 상품·표현·상황에 실제 적용됨. NOT_APPLICABLE: 광고 내용만으로 선행조건 불충족이 확정됨. UNDETERMINED: 매체·랜딩·상품정본·운영이력 등 외부입력이 없어 적용성부터 확정할 수 없음.
3. APPLICABLE이면 COMPLIANT/VIOLATION/UNDETERMINED 중 하나로 판정한다. 필수 문구가 광고 전체에 없고 파서 커버리지가 READY면 VIOLATION이 가능하다. 외부 정본이나 이미지 의미가 필요하면 UNDETERMINED다.
4. 단순히 관련 문구가 없다는 이유로 조건부 규칙을 NOT_APPLICABLE로 만들지 말라. 예: 매체유형이 없으면 전자전송 광고 규칙은 UNDETERMINED다.
5. 형식·문구의 허용 여부와 필수 구성요소는 입력된 규제목록 v2의 해당 항목 판정기준만으로 판단한다. 다른 광고에서 본 표현이나 별도 사례 규칙을 일반화하지 않는다.
6. 근거는 documents의 evidence_id와 실제 line_ref만 사용한다. 부재 판정은 evidence_id를 비워도 되지만 reason에 광고 전체 검사임을 명시한다.
7. 이 결과는 연구원 검수 전 silver 초안이다. 자신 없으면 억지로 확정하지 말고 UNDETERMINED를 선택한다.
8. legal_basis·supporting_rules·basis_details는 같은 규제목록 v2에 기록된 근거다. 점검문구와 판정기준을 해석할 때 함께 사용하되, 한 사례의 규칙 ID를 다른 모든 광고의 규칙 ID로 치환하지 않는다.
9. source_sheet가 신규규칙후보인 T 항목도 사용자가 사용 가능하다고 확정한 v2 규칙이다. 필수여부 O는 적용 템플릿의 필수 항목으로 검사하고, △는 기재요령의 조건이 확인될 때만 필수로 검사한다.
10. 판정기준에 여러 구성요소가 `·`, 쉼표, `및`, `함께` 등으로 열거되면 requirement_checks에서 각각 확인한다. 하나만 보인다는 이유로 전체 충족으로 판정하지 않는다. 단, `또는`처럼 대안임이 명시된 조건은 대안 묶음으로 설명한다.
11. 표시의무의 필수 요소가 없으면 MISSING, 금지·오기재 조건에 걸리면 VIOLATED로 쓴다. 광고나 외부입력만으로 확인할 수 없으면 UNDETERMINED다.
12. 예시문구의 `~`, `-`, `*`, 불릿 종류, 날짜 표면형식은 판정기준이 정확한 형식을 의무로 명시하지 않는 한 의미상 동등 표현을 허용한다. 예시와 글자 모양이 다르다는 이유만으로 위반 처리하지 않는다.
13. T 규칙을 APPLICABLE로 판단하려면 해당 템플릿/세부상품이 광고 본문에서 확인되는 근거 또는 status가 confirmed인 메타데이터가 필요하다. inferred 템플릿 값이나 필수 문구의 부재만으로 T 규칙 적용성을 확정하지 말고, 서로 배타적인 템플릿 규칙을 동시에 적용하지 않는다.

14. A mere statement that an item exists or may be charged never satisfies a rule that also requires attributes such as formula, rate, period, amount, conditions, or exemptions. Check every required attribute separately. If the full advertisement lacks a required attribute and parser_coverage is READY, mark that component MISSING.
15. CONFIRMED_METADATA may be used only with the exact routing field names listed in applicability_metadata_fields, and every listed field must have status confirmed, verified, or provided. For a T rule, APPLICABLE is allowed only when template_id is confirmed and exactly matches that rule's product_subtype. Advertisement text alone may suggest a template, but it must remain UNDETERMINED until the ad-level template is confirmed.

JSON 객체 하나만 출력한다:
{
  "ad_id": "...",
  "results": [
    {
      "item_id": "...",
      "applicability": "APPLICABLE|NOT_APPLICABLE|UNDETERMINED",
      "applicability_basis": "ADVERTISEMENT_EVIDENCE|CONFIRMED_METADATA|NOT_APPLICABLE|UNDETERMINED",
      "applicability_evidence_ids": ["..."],
      "applicability_evidence_line_refs": ["..."],
      "applicability_metadata_fields": ["template_id|product_subtype|ad_type|product_name_shown|media_type|product_group"],
      "verdict": "COMPLIANT|VIOLATION|NOT_APPLICABLE|UNDETERMINED",
      "evidence_ids": ["..."],
      "evidence_line_refs": ["..."],
      "requirement_checks": [
        {
          "requirement": "판정기준의 개별 구성요소 또는 대안 묶음",
          "status": "SATISFIED|MISSING|VIOLATED|NOT_APPLICABLE|UNDETERMINED",
          "evidence_ids": ["..."],
          "evidence_line_refs": ["..."],
          "reason": "짧은 근거"
        }
      ],
      "reason": "한두 문장",
      "confidence": "LOW|MEDIUM|HIGH",
      "needs_researcher_review": true
    }
  ]
}
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def product_applies(groups: list[str], product: str) -> bool:
    return "전체" in groups or product in groups


def load_cd_rules() -> list[dict[str, Any]]:
    items, _ = v2_source.build()
    rows = []
    for item in items:
        groups = list(item["적용상품"])
        poc_product = (
            product_applies(groups, "대출성")
            or product_applies(groups, "예금성")
        )
        # The 104-item scope is derived entirely from v2 columns: 124 items
        # apply to loan/deposit/overall, and the 20 rows whose v2 judgment type
        # is layout-required remain deferred as previously decided.
        if not poc_product or item["판정유형"] == "레이아웃필요":
            continue
        rows.append({
            "item_id": item["id"],
            "category": item["category"],
            "category_label": item["구분"],
            "title": item["title"],
            "question": item["question"],
            "criterion": item["criterion"],
            "product_groups": groups,
            "product_subtype": item.get("세부상품") or None,
            "judgment_mode": item["판정모드"],
            "judgment_type": item["판정유형"],
            "input_requirement": item["입력요건"],
            "required_medium": item["필요매체"],
            "violation_grade": item["위반등급"],
            "legal_basis": item["근거법령"],
            "representative_rule_id": item["대표규칙"],
            "supporting_rules": item["규칙근거"],
            "rule_summaries": item["규칙요약"],
            "basis_details": item["근거상세"],
            "v2_note": item["비고"],
            "source_sheet": "실행_점검항목",
        })
    if len(rows) != 104:
        raise RuntimeError(f"v2 C/D 실행범위가 104개가 아님: {len(rows)}")
    return rows


def load_t_rules() -> list[dict[str, Any]]:
    return load_template_candidate_rules()


def evidence_documents(ad: dict[str, Any]) -> list[dict[str, Any]]:
    documents = []
    for asset in ad["assets"]:
        for page in asset["pages"]:
            for unit in page["evidence_units"]:
                if unit["evidence_role"] != "primary" or not unit["search_eligible"]:
                    continue
                text = str(unit.get("final_text") or "").strip()
                if not text:
                    continue
                documents.append({
                    "evidence_id": unit["evidence_id"],
                    "page_no": page["page_no"],
                    "region_id": unit.get("region_id"),
                    "gubun": unit.get("gubun"),
                    "line_refs": unit["line_refs"],
                    "text": text,
                })
    return documents


def main() -> None:
    # Historical chunk conversion is needed only by this development-data CLI.
    # The operational runner imports SYSTEM/load_cd_rules and must not inherit
    # a dependency on the old ad-review-input-v1 converter.
    from build_review_input_v1 import build_ad, search_docs

    if OUT is None or INPUTS is None or not ADS or not RUN_NAME:
        raise RuntimeError("데이터셋 래퍼가 OUT·INPUTS·ADS·RUN_NAME을 명시해야 합니다.")
    OUT.mkdir(parents=True, exist_ok=True)
    INPUTS.mkdir(parents=True, exist_ok=True)
    cd_rules = load_cd_rules()
    t_rules = load_t_rules()
    requests = []
    manifest_ads = []
    all_coarse = []
    all_fine = []

    for ad_id in ADS:
        chunk_path = CHUNKS / f"{ad_id}.json"
        ad = build_ad(chunk_path)
        if ad["quality"]["unread_regions"]:
            raise RuntimeError(f"미판독 영역이 있는 광고는 표본 제외: {ad_id}")
        write_json(INPUTS / f"{ad_id}.json", ad)
        coarse, fine = search_docs([ad])
        all_coarse.extend(coarse)
        all_fine.extend(fine)

        product = ad["routing"]["product_group"]
        template_id = ad["routing"]["template_id"]
        rules = [row for row in cd_rules if product_applies(row["product_groups"], product)]
        # T rows are active v2 rules. Route them broadly by the v2 product
        # family; template and O/△ conditions are resolved by judgment.
        matching_t = [row for row in t_rules if product_applies(row["product_groups"], product)]
        rules.extend(matching_t)
        rules.sort(key=lambda row: (row["category"], row["item_id"]))
        docs = evidence_documents(ad)
        category_counts = Counter(row["category"] for row in rules)
        t_ids = [row["item_id"] for row in matching_t]

        batches = []
        for category in ("PRESENCE", "PROHIBIT", "STYLE"):
            category_rules = [row for row in rules if row["category"] == category]
            for offset in range(0, len(category_rules), BATCH_SIZE):
                batch = category_rules[offset:offset + BATCH_SIZE]
                request_id = f"{RUN_NAME}:{ad_id}:{category}:{offset // BATCH_SIZE + 1}"
                user_payload = {
                    "request_id": request_id,
                    "ad_id": ad_id,
                    "routing": ad["routing"],
                    "routing_quality": ad["routing_quality"],
                    "parser_coverage": "READY",
                    "documents": docs,
                    "rules": batch,
                }
                requests.append({
                    "request_id": request_id,
                    "ad_id": ad_id,
                    "category": category,
                    "requested_item_ids": [row["item_id"] for row in batch],
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                })
                batches.append(request_id)
        manifest_ads.append({
            "ad_id": ad_id,
            "product_group": product,
            "product_subtype": ad["routing"]["product_subtype"],
            "template_id": template_id,
            "source_chunk": str(chunk_path),
            "source_chunk_sha256": sha256(chunk_path),
            "evidence_units": len(docs),
            "fine_views": len(fine),
            "routed_cd_rules": len(rules) - len(matching_t),
            "matching_t_rules": t_ids,
            "rules_checked": len(rules),
            "category_counts": dict(category_counts),
            "request_ids": batches,
        })

    coarse_path = OUT / "03_검색청크_영역.jsonl"
    fine_path = OUT / "03_검색청크_세부.jsonl"
    coarse_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_coarse), encoding="utf-8")
    fine_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_fine), encoding="utf-8")
    request_path = OUT / "gemma_exhaustive_requests.jsonl"
    request_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in requests), encoding="utf-8")
    manifest = {
        "schema_version": f"researcher-answer-{RUN_NAME}-input-v1",
        "status": "silver_generation_input",
        "source_of_truth": {
            "file": str(v2_source.AGENT),
            "sha256": sha256(Path(v2_source.AGENT)),
            "sheets": ["실행_점검항목", "신규규칙후보"],
        },
        "coverage_policy": {
            "fixed_rules_per_ad": False,
            "cd_rules": "상품군 라우팅을 통과한 v2 PoC 104개 항목을 전부 검사",
            "t_rules": "사용 확정된 v2 T 규칙을 상품군으로 전개; 템플릿 및 O/△ 조건은 적용성 판단 자료",
            "search_top_k_used_as_gold_gate": False,
            "parser_labels_used_as_exclusion_gate": False,
            "case_derived_rules": "forbidden; each item is judged only from its regulation-v2 criterion",
        },
        "counts": {
            "ads": len(ADS),
            "loan_ads": sum(ad_id.endswith("대출성") for ad_id in ADS),
            "deposit_ads": sum(ad_id.endswith("예금성") for ad_id in ADS),
            "requests": len(requests),
            "total_rule_checks": sum(row["rules_checked"] for row in manifest_ads),
            "coarse_evidence": len(all_coarse),
            "fine_evidence": len(all_fine),
        },
        "ads": manifest_ads,
    }
    write_json(OUT / "coverage_manifest.json", manifest)
    print(json.dumps({"output": str(OUT), **manifest["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit("직접 실행 금지: prepare_answer10_current.py를 사용하세요.")
