"""Build source-bound policies from the reviewed template snapshot and approved revision."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from rag.templates.methodology import parse_methodology_workbook
from rag.judgment.review_program_extensions import extend_policies


def atom(number, text, owner="LLM", adapter=None):
    result = {"obligation_id": f"O{number}", "text": text,
              "owners": {"rule": bool(adapter), "llm": owner == "LLM",
                         "external_input": owner == "EXTERNAL", "human": owner == "HUMAN"},
              "evidence": {"advertisement_direct_quote_required": owner != "HUMAN",
                           "absence_requires_complete_scan": True,
                           "same_advertisement_product_revision_scope": True,
                           "rule_or_example_text_is_advertisement_evidence": False},
              "retrieval_queries": [text], "interpretation_hints": []}
    if adapter:
        result["deterministic_adapter"] = adapter
    return result


def ref(n):
    return {"ref": f"O{n}"}


def fact(n):
    return {"fact": n}


def allof(*nodes):
    return {"all": list(nodes)}


def anyof(*nodes):
    return {"any": list(nodes)}


def branch(c, yes, no):
    return {"if": [c, yes, no]}


def unknown(reason):
    return {"unknown": reason}


def build(base, sourcebook, approved):
    if base.get('source_binding_sha256') != '965e7fd6347ae137d4b8ca74444ccaeb52a507aadfa3bc2769ccedb17f1b03ff':
        raise ValueError('source snapshot changed: semantic policies require review')
    approved_hashes = {
        '4568f05002abf0b0fd31c1a0fc6eedd4cb6ac027811adc2ed51ce0b906e15e1a',
        '0cc89199860a40f6660e0b1bfd73a0a0b14b25707c9128218914662d3e9e8f41',
        '0020c891dcd685b87d9ad123f43bbf146a23887281adaccfa9a752a0e19ea45e'}
    if {hashlib.sha256(p.read_bytes()).hexdigest() for p in approved.glob('*심의방법.xlsx')} != approved_hashes:
        raise ValueError('ISA revision differs from the approved source snapshot')
    by_id = {p["plan_id"]: p for p in base["plans"]}
    source_hash = hashlib.sha256(sourcebook.read_bytes()).hexdigest()
    policies = {}

    def scoped(policy):
        policy["applicability_inputs"] = [copy.deepcopy(by_id[policy["plan_id"]]["applicability_inputs"][0])]
        policy["applicability_logic"] = allof(fact("A1"))

    def checks(policy, rows, logic=None):
        policy["obligations"] = rows
        policy["obligation_logic"] = logic or allof(*(ref(i) for i in range(1, len(rows) + 1)))

    for plan in base["plans"]:
        if plan["source"]["source_kind"] != "TEMPLATE":
            continue
        fields = plan["source"]["source_fields"]
        kinds = ["PRESENCE" if fields["label"] in {"회사명", "상품명", "가입대상"} else "SEMANTIC"]
        if any(a["owners"]["human"] for a in plan["obligations"]):
            kinds.append("VISUAL")
        if any(a["owners"]["external_input"] for a in plan["obligations"]):
            kinds.append("EXTERNAL")
        if len(plan["applicability_inputs"]) > 1:
            kinds.append("CONDITIONAL")
        policy = {"plan_id": plan["plan_id"], "base_source_sha256": plan["source_sha256"],
                  "program": {"mode": "AUTOMATIC", "kinds": kinds,
                              "allowed_outcomes": ["COMPLIANT", "VIOLATION", "UNDETERMINED"],
                              "source_refs": [{"plan_id": plan["plan_id"], "source_sha256": plan["source_sha256"]}],
                              "semantic_status": "SOURCE_CRITERIA_PRESERVED",
                              "unsupported_input_policy": "UNDETERMINED"}}
        if not plan["source"].get("source_provenance"):
            policy["source_revision"] = {"source_provenance": {
                "filename": sourcebook.name, "sha256": source_hash,
                "record_number": int(plan["plan_id"].split("-")[-1]),
                "locator": "numbered mapping workbook record"}}
        text = " ".join(str(v or "") for v in fields.values())
        if re.search(r"부적정\s*판단하지\s*않음", text):
            policy["program"]["allowed_outcomes"] = ["COMPLIANT", "UNDETERMINED"]
            policy["program"]["kinds"].append("REVIEW_REQUEST")
            if "생성형 AI" in text or fields["label"] == "회사명":
                scoped(policy)
        if re.search(r"적정\s*/\s*부적정\s*판단하지\s*않음", str(fields.get("satisfied") or "")):
            scoped(policy)
            policy["program"].update(mode="REVIEW_ONLY", kinds=["REVIEW_REQUEST"],
                                     allowed_outcomes=["UNDETERMINED"],
                                     review_question=fields.get("review_guidance") or fields.get("review"))
            checks(policy, [], unknown("SOURCE_REVIEW_ONLY"))
        policies[plan["plan_id"]] = policy

    revised = 0
    for workbook in sorted(approved.glob("*심의방법.xlsx")):
        catalog = parse_methodology_workbook(workbook)
        rows = [r for r in catalog["rows"] if r.get("decision_mode") == "PRESENCE_ONLY"]
        if len(rows) != 1:
            raise ValueError("approved ISA workbook needs exactly one presence-only revision")
        row = rows[0]
        matched = [p for p in base["plans"] if str(p["source"].get("product_template") or "").split(" [")[0]
                   == row["template_section"] and p["source"]["label"] == "수수료"]
        if len(matched) != 1:
            raise ValueError("approved revision must map to exactly one canonical source")
        plan = matched[0]
        policy = policies[plan["plan_id"]]
        fields = copy.deepcopy(plan["source"]["source_fields"])
        for dest, src in [("satisfied", "appropriate_judgment"), ("violated", "inappropriate_judgment"),
                          ("violation_guidance", "inappropriate_guidance"), ("review", "review_needed_judgment"),
                          ("review_guidance", "review_needed_guidance")]:
            fields[dest] = row[src]
        policy["source_revision"] = {"source_fields": fields, "source_provenance": row["source"]}
        policy["program"]["kinds"] = ["PRESENCE"]
        policy["program"]["source_refs"].append(row["source"])
        scoped(policy)
        checks(policy, [atom(1, "수수료 또는 보수의 부과·발생 사실이나 발생 가능성이 기재되어 있는가. 비율·금액·연 표시는 이 존재확인 요건이 아니다.")])
        revised += 1
    if revised != 3:
        raise ValueError("all three approved ISA revisions are required")

    groups = [([f"MTH-DEPOSIT-DEMAND-R{i:02}" for i in (7, 8, 9)], True, True),
              ([f"TPL-MAP-{i:03}" for i in (78, 79, 80)], False, False),
              ([f"TPL-MAP-{i:03}" for i in (100, 101, 102)], False, False)]
    for ids, month, cap in groups:
        texts = ["방식1: 기본금리가 표시되는가", "방식2: 최고금리가 표시되는가",
                 "방식3: 최저금리부터 최고금리까지 범위가 표시되는가", "방식2의 기본금리 수치가 별도로 표시되는가",
                 "연 기준 또는 원문에서 허용한 12개월 기준이 표시되는가", "세전 여부가 표시되는가",
                 "금리에 연결된 기준일이 심의일 전 " + ("한 달" if month else "30일") + " 이내인가"]
        rows = [atom(i + 1, text, adapter={"kind": "BASIS_DATE_WITHIN", "unit": "CALENDAR_MONTH" if month else "DAYS",
                                        "amount": 1 if month else 30} if i == 6 else None)
                for i, text in enumerate(texts)]
        ways = [ref(1), allof(ref(2), ref(4)), ref(3)]
        if cap:
            rows.append(atom(8, "방식2 또는 방식3의 최고금리가 적용되는 금액 한도가 표시되는가"))
            ways = [ref(1), allof(ref(2), ref(4), ref(8)), allof(ref(3), ref(8))]
        for item_id in ids:
            policy = policies[item_id]
            scoped(policy)
            checks(policy, copy.deepcopy(rows), allof(anyof(*ways), ref(5), ref(6), ref(7)))
            policy["program"].update(kinds=["ALTERNATIVE", "NUMERIC_DATE", "PRESENCE"],
                                     logical_group_id=ids[0], logical_group_members=ids,
                                     semantic_status="AUTHORED_BRANCHES")
            policy["program"]["source_refs"] = [{"plan_id": i, "source_sha256": by_id[i]["source_sha256"]} for i in ids]

    policy = policies["MTH-DEPOSIT-DEMAND-R15"]
    scoped(policy)
    policy["applicability_inputs"] += [
        {"fact_id": "B1", "name": "확정 매체가 LMS인가", "owner": "RULE", "type": "CONFIRMED_METADATA",
         "metadata_key": "media_type", "equals": "LMS", "purpose": "DECISION_BRANCH", "unknown_policy": "UNDETERMINED"},
        {"fact_id": "B2", "name": "광고에 링크가 포함되어 있는가", "owner": "LLM", "type": "ADVERTISEMENT_OBSERVATION",
         "purpose": "DECISION_BRANCH", "unknown_policy": "UNDETERMINED", "absence_policy": "NOT_SATISFIED_IF_COMPLETE_AD_SCAN"}]
    checks(policy, [atom(1, "원문 예금자보호 안내의 의미가 기재되어 있는가"), atom(2, "원본의 예금자보호 로고가 확인되는가", "HUMAN")],
           allof(ref(1), branch(fact("B1"), branch(fact("B2"), unknown("LMS_LINK_SOURCE_CONFLICT"), {"not": fact("B2")}), ref(2))))
    policy["program"].update(kinds=["CONDITIONAL", "SEMANTIC", "VISUAL", "EXTERNAL"],
                             semantic_status="AUTHORED_BRANCHES_WITH_SOURCE_CONFLICT",
                             review_question="LMS 링크가 있으면 연결 페이지 로고와 원문 기준 충돌을 확인하십시오.")
    for item_id in ("TPL-MAP-081", "TPL-MAP-103"):
        policy = policies[item_id]
        scoped(policy)
        policy["applicability_inputs"].append({"fact_id": "A2", "name": "확인된 상품자료상 우대금리가 존재하는가",
            "owner": "LLM_EXTERNAL", "type": "AD_AND_EXTERNAL", "unknown_policy": "UNDETERMINED"})
        policy["applicability_logic"] = allof(fact("A1"), fact("A2"))
        checks(policy, [atom(1, "우대금리와 우대조건이 표시되어 있는가"),
                       atom(2, "같은 상품·기간·연 단위에서 최대 우대금리가 전체 조건별 우대금리 합 이하인가", adapter={"kind": "BONUS_SUM_BOUND"})])
        policy["program"]["kinds"] = ["CONDITIONAL", "NUMERIC_DATE", "EXTERNAL"]
    policy = policies["MTH-DEPOSIT-DEMAND-R10"]
    scoped(policy)
    policy["applicability_inputs"].append({"fact_id": "B1", "name": "확인된 상품자료상 우대금리가 존재하는가",
        "owner": "LLM_EXTERNAL", "type": "AD_AND_EXTERNAL", "purpose": "DECISION_BRANCH", "unknown_policy": "UNDETERMINED"})
    checks(policy, [atom(1, "여러 조건 중 일정 개수 이상 충족하면 우대금리를 주는 방식이 표시되는가"),
                   atom(2, "최대 우대금리가 전체 조건별 우대금리 합 이하인가", adapter={"kind": "BONUS_SUM_BOUND"}),
                   atom(3, "기본금리만 표시하는 방식1의 기재가 있는가")],
           anyof(ref(1), branch(fact("B1"), ref(2), ref(3))))
    policy["program"]["kinds"] = ["ALTERNATIVE", "CONDITIONAL", "NUMERIC_DATE", "EXTERNAL"]
    return extend_policies(base, {"schema_version": "review-program-v1", "approved_date": "2026-09-22",
            "source_policy": "TEMPLATE_ONLY", "answers_loaded": False, "plans": list(policies.values())})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--source-workbook", required=True, type=Path)
    parser.add_argument("--approved-methodology", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    policy = build(json.loads(args.base.read_text(encoding="utf-8")), args.source_workbook, args.approved_methodology)
    args.output.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
