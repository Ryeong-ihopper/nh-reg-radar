"""Explicit deposit-methodology decomposition for local review, not activation.

This is an authored interpretation of the version-bound methodology, not a
keyword-to-rule compiler. Original clauses remain attached to each plan.
"""
from __future__ import annotations

import hashlib
import json

from rag.judgment.structured_predicates import validate_plan


def fact(name: str) -> dict:
    return {"fact": name}


def all_of(*nodes: dict) -> dict:
    return {"all": list(nodes)}


def any_of(*nodes: dict) -> dict:
    return {"any": list(nodes)}


def choose(condition: dict, yes: dict, no: dict) -> dict:
    return {"if": [condition, yes, no]}


def unknown(reason: str) -> dict:
    return {"unknown": reason}


FACTS = {
    "selected_scope": ("CONTEXT", "METADATA", "입출식 예금 심의방법 선택 확인"),
    "company_name": ("LLM", "ADVERTISEMENT", "광고주 회사명 표시"),
    "product_name": ("LLM", "ADVERTISEMENT", "광고 대상 상품명 표시"),
    "eligibility": ("LLM", "ADVERTISEMENT", "가입대상 설명 표시"),
    "method_one": ("LLM", "ADVERTISEMENT", "금리 방식1에 해당하는 표시"),
    "method_two": ("LLM", "ADVERTISEMENT", "금리 방식2에 해당하는 표시"),
    "method_three": ("LLM", "ADVERTISEMENT", "금리 방식3에 해당하는 표시"),
    "annual": ("EXTRACTOR", "ADVERTISEMENT", "연 기준 또는 12개월 표시"),
    "before_tax": ("EXTRACTOR", "ADVERTISEMENT", "세전 표시"),
    "basis_date": ("EXTRACTOR", "ADVERTISEMENT", "금리에 연결된 기준일 표시"),
    "base_rate": ("EXTRACTOR", "ADVERTISEMENT", "방식2의 기본금리 수치 표시"),
    "maximum_cap": ("LLM", "ADVERTISEMENT", "최고금리 적용 금액 한도 표시"),
    "has_bonus": ("CONTEXT", "PRODUCT_DOCUMENT", "해당 상품에 우대금리 존재 여부"),
    "threshold_scheme": ("LLM", "ADVERTISEMENT", "여러 조건 중 n개 충족 시 우대금리 제공 표시"),
    "bonus_cap": ("LLM", "ADVERTISEMENT", "방식1의 우대금리 적용 금액 한도 표시"),
    "payment_time": ("LLM", "ADVERTISEMENT", "이자 지급시기 표시"),
    "seizure_restriction": ("LLM", "ADVERTISEMENT", "압류 등 원금·이자 지급제한의 의미 표시"),
    "certificate_restriction": ("LLM", "ADVERTISEMENT", "잔액증명서 당일 거래 제한의 의미 표시"),
    "protection_text": ("LLM", "ADVERTISEMENT", "예금자보호 안내의 의미 표시"),
    "lms": ("CONTEXT", "METADATA", "확정된 광고 매체가 LMS인지"),
    "has_link": ("EXTRACTOR", "ADVERTISEMENT", "LMS에 링크 포함 여부"),
    "protection_logo": ("HUMAN", "RENDER", "원본의 예금자보호 로고 확인"),
    "explanation_right": ("LLM", "ADVERTISEMENT", "설명받을 권리 및 이해 후 거래 안내"),
    "terms": ("LLM", "ADVERTISEMENT", "약관·상품설명서 확인 안내"),
    "ai_notice": ("LLM", "ADVERTISEMENT", "생성형 AI 활용 안내 표시"),
    "approval_issuer": ("EXTRACTOR", "ADVERTISEMENT", "심의주체 표기 형식"),
    "approval_number": ("EXTRACTOR", "ADVERTISEMENT", "심의필 번호 형식"),
    "approval_dates": ("EXTRACTOR", "ADVERTISEMENT", "유효기간 시작·종료 표시 형식"),
}

FACT_EXTRACTION_INSTRUCTIONS = """Return proposed observations for each requested fact,
with short exact evidence citations, source location and the matching advertisement,
product, revision and offer scope. Return UNKNOWN for missing or ambiguous inputs.
Do not return an overall verdict or set verification flags yourself; an independent
adapter/reviewer must validate observations before the predicate calculator runs.
Source examples describe meaning only: do not copy their names, dates or values as
advertisement evidence. A missing search hit is not a complete absence scan.
Keep alternate display methods separate. All values in a sum must share units,
rate basis and offer scope; preserve every component. Product-level absence of a
bonus requires product information; silence in an advertisement does not prove it.
Visual-logo facts belong to HUMAN, not a text LLM. Do not resolve source conflicts.
Synthetic examples, not legal criteria or advertisement answers:
- maximum=0.3, complete components=[0.1,0.2] in the same annual unit: propose these
  values separately; do not perform or invent the final legal judgment.
- only one component retrieved and total component count unknown: completeness
  is unknown even if the observed component is enough for a favorable comparison.
- item has no cited example: use its obligation/criterion to locate evidence;
  never infer absence because there was no example or no retrieval match.
"""


def compile_deposit_plans(rules: list[dict]) -> list[dict]:
    rows = {r["source"]["excel_row"]: r for r in rules
            if r["rule_id"].startswith("MTH-DEPOSIT-DEMAND-")}
    if set(rows) != set(range(4, 20)):
        raise ValueError("deposit source must contain exactly rows 4..19")
    expected_sha = "f79f7d5a7ca19e9508b13e5e11c82684a8d9d65cef6d260b4f50aa570d93f31b"
    if any(r["source"]["original_sha256"] != expected_sha for r in rows.values()):
        raise ValueError("new source version needs re-review of authored expressions")
    plans = []

    def add(name: str, row_numbers: list[int], expression: dict,
            on_false: str = "VIOLATION") -> None:
        scope = fact("selected_scope")
        keys: set[str] = set()

        def collect(node: dict) -> None:
            op, arg = next(iter(node.items()))
            if op == "fact":
                keys.add(arg)
            elif op == "le_sum":
                keys.update(arg)
            elif op in {"all", "any", "if"}:
                for child in arg:
                    collect(child)
            elif op == "not":
                collect(arg)
        collect(scope)
        collect(expression)
        specs = {}
        for key in sorted(keys):
            if key in {"bonus_maximum", "bonus_components"}:
                specs[key] = {"type": "decimal" if key == "bonus_maximum" else "decimal_list",
                              "unit": "annual_percentage_points", "owner": "EXTRACTOR",
                              "sources": ["ADVERTISEMENT"], "description": key}
            else:
                owner, source, description = FACTS[key]
                specs[key] = {"type": "bool", "owner": owner, "sources": [source],
                              "description": description,
                              "false_requires_scan": key in {
                                  "company_name", "product_name", "eligibility", "annual",
                                  "before_tax", "basis_date", "base_rate", "maximum_cap",
                                  "bonus_cap", "payment_time", "seizure_restriction",
                                  "certificate_restriction", "protection_text", "has_link",
                                  "protection_logo", "explanation_right", "terms", "ai_notice"}}
        refs = [{"rule_id": rows[n]["rule_id"], **rows[n]["source"],
                 "outcomes": rows[n]["outcomes"],
                 "semantic_reference": rows[n]["display_example"],
                 "semantic_reference_policy": "MEANING_ONLY_NEVER_AD_EVIDENCE_OR_EXACT_VALUE"}
                for n in row_numbers]
        plan = {"plan_id": f"DEPOSIT-DEMAND-{name}", "facts": specs, "scope": scope,
                "expression": expression, "on_false": on_false, "source_refs": refs,
                "fact_extraction_instructions": FACT_EXTRACTION_INSTRUCTIONS,
                "retrieval_plan": {
                    "required_queries": [{"fact": key, "meaning": spec["description"]}
                                         for key, spec in specs.items()
                                         if "ADVERTISEMENT" in spec["sources"]],
                    "example_query_role": "OPTIONAL_SEPARATE_SUPPLEMENT",
                    "no_example_does_not_remove_required_queries": True,
                    "absence_requires_complete_scan": True,
                    "operationally_connected": False},
                "status": "LOCAL_EXECUTABLE_NOT_OPERATIONALLY_CONNECTED",
                "source_binding_sha256": hashlib.sha256(json.dumps(
                    refs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
        validate_plan(plan)
        plans.append(plan)

    add("COMPANY", [4], fact("company_name"), "REVIEW_REQUIRED")
    add("PRODUCT", [5], fact("product_name"))
    # Old template permits omission for unrestricted eligibility; precedence unresolved.
    add("ELIGIBILITY", [6], choose(fact("eligibility"), fact("eligibility"),
                                  unknown("OLD_NEW_ELIGIBILITY_OMISSION_CONFLICT")))
    methods = any_of(fact("method_one"),
                     all_of(fact("method_two"), fact("base_rate"), fact("maximum_cap")),
                     all_of(fact("method_three"), fact("maximum_cap")))
    add("RATE", [7, 8, 9], all_of(methods, fact("annual"), fact("before_tax"),
                                   fact("basis_date"), unknown("ONE_MONTH_VERSUS_30_DAYS_POLICY")))
    add("BONUS", [10], choose(fact("has_bonus"),
                              any_of(fact("threshold_scheme"),
                                     {"le_sum": ["bonus_maximum", "bonus_components"]}),
                              fact("method_one")))
    # Methods2/3 already require cap in RATE; the exemption only removes repetition.
    add("BONUS-CAP", [11], any_of(fact("method_two"), fact("method_three"),
                                 all_of(fact("method_one"), any_of(
                                     {"not": fact("has_bonus")}, fact("bonus_cap")))))
    for name, row, key in [("PAYMENT", 12, "payment_time"),
                           ("SEIZURE", 13, "seizure_restriction"),
                           ("CERTIFICATE", 14, "certificate_restriction")]:
        add(name, [row], fact(key))
    # LMS + link has conflicting violation/review instructions: never invent precedence.
    logo = choose(fact("lms"), choose(fact("has_link"),
                  unknown("LMS_LINK_LOGO_VIOLATION_REVIEW_CONFLICT"),
                  {"not": fact("has_link")}), fact("protection_logo"))
    add("PROTECTION", [15], all_of(fact("protection_text"), logo))
    for name, row, key in [("RIGHTS", 16, "explanation_right"), ("TERMS", 17, "terms")]:
        add(name, [row], all_of(fact(key), unknown("LOAN_LINE_TERM_IN_DEPOSIT_SOURCE")))
    add("AI", [18], fact("ai_notice"), "REVIEW_REQUIRED")
    add("APPROVAL", [19], all_of(fact("approval_issuer"), fact("approval_number"),
                                  fact("approval_dates")))
    return plans
