"""Bounded deterministic checks for explicit arithmetic claims in advertisements."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from rag.judgment.reading_quality import needs_reading_review


METHOD = "CANONICAL_EXPLICIT_ARITHMETIC"
_EQUATION = re.compile(
    r"(?P<left>\d+(?:\.\d+)?(?:\s*[%％]?[pP]?\s*[+\-]\s*(?:[가-힣A-Za-z·]+\s*)?\d+(?:\.\d+)?\s*[%％]?[pP]?)+)"
    r"\s*=\s*(?:(?:최종|합계|총)\s*)?(?P<right>\d+(?:\.\d+)?)\s*[%％]?[pP]?"
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_CALCULATION_SIGNAL = re.compile(
    r"(?:합계|총액|산식|계산\s*예시|수취이자|환급액|"
    r"최대\s*우대금리|우대금리\s*최대|[+\-=])"
)


def _calculate(left: str) -> Decimal | None:
    tokens = re.findall(r"\d+(?:\.\d+)?|[+\-]", left)
    if not tokens or not _NUMBER.fullmatch(tokens[0]) or len(tokens) % 2 == 0:
        return None
    try:
        value = Decimal(tokens[0])
        for index in range(1, len(tokens), 2):
            operand = Decimal(tokens[index + 1])
            value = value + operand if tokens[index] == "+" else value - operand
        return value
    except InvalidOperation:
        return None


def calculate_explicit_arithmetic(payload: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve D-163 without an LLM; calculate only machine-readable claims.

    Exact source-written ``a+b-c=d`` expressions are calculated. A complete
    scan with no calculation relationship is NOT_APPLICABLE. A relationship
    that is visible but not safely machine-readable remains UNDETERMINED for a
    reviewer instead of being guessed by either code or a model.
    """
    contract = rule.get("condition_contract") or {}
    obligations = contract.get("obligation_checks") or []
    adapters = [value.get("deterministic_adapter") or {} for value in obligations]
    if not any(value.get("kind") == "ADVERTISED_ARITHMETIC_CONSISTENCY" for value in adapters):
        return None
    scope = (payload.get("evidence_scope") or {}).get(rule.get("item_id")) or {}
    if (payload.get("parser_coverage") != "READY" or not scope.get("complete_ad_scan")
            or (payload.get("reading_quality") or {}).get("global_scan_incomplete") is True):
        return _undetermined(rule, contract, [], [], "광고 전체 판독이 완료되지 않아 산술관계를 확정할 수 없습니다.")
    allowed = set(map(str, scope.get("evidence_ids") or []))
    equations: list[tuple[str, str, Decimal, Decimal, str]] = []
    signal_ids: list[str] = []
    signal_refs: list[str] = []
    for document in payload.get("documents") or []:
        if str(document.get("evidence_id")) not in allowed or needs_reading_review(document):
            continue
        line_texts = document.get("line_texts") or {}
        for line_ref in document.get("line_refs") or []:
            text = str(line_texts.get(line_ref) or "")
            if _CALCULATION_SIGNAL.search(text) and len(_NUMBER.findall(text)) >= 2:
                signal_ids.append(str(document["evidence_id"]))
                signal_refs.append(str(line_ref))
            for match in _EQUATION.finditer(text):
                calculated = _calculate(match.group("left"))
                if calculated is not None:
                    equations.append((str(document["evidence_id"]), str(line_ref), calculated,
                                      Decimal(match.group("right")), match.group(0)))
    if not equations:
        signal_ids = list(dict.fromkeys(signal_ids))
        signal_refs = list(dict.fromkeys(signal_refs))
        if signal_ids:
            return _undetermined(
                rule, contract, signal_ids, signal_refs,
                "계산 관계는 표시되어 있으나 안전하게 계산할 수 있는 명시 산식으로 판독되지 않았습니다.",
                matched=True,
            )
        return _not_applicable(rule, contract)
    mismatch = [value for value in equations if value[2] != value[3]]
    ids = list(dict.fromkeys(value[0] for value in equations))
    refs = list(dict.fromkeys(value[1] for value in equations))
    details = "; ".join(
        "검산: "
        + re.sub(r"\s*[%％]?[pP]?\s*", "", claim.split("=", 1)[0])
        + (" != " if calculated != advertised else " = ")
        + str(advertised)
        for _, _, calculated, advertised, claim in equations
    )
    status = "VIOLATED" if mismatch else "SATISFIED"
    verdict = "VIOLATION" if mismatch else "COMPLIANT"
    conditions = []
    for condition in contract.get("applicability_conditions") or []:
        conditions.append({
            "condition_ref": condition["condition_id"], "status": "SATISFIED",
            "evidence_ids": ids, "evidence_line_refs": refs,
        })
    checks = []
    for obligation in obligations:
        checks.append({
            "obligation_ref": obligation["obligation_id"],
            "requirement": obligation["text"], "status": status,
            "finding_basis": "OBSERVED", "evidence_ids": ids,
            "evidence_line_refs": refs, "reason": details,
        })
    return {
        "item_id": rule["item_id"],
        "scope_check": {"scope_ref": contract.get("scope_ref", "SCOPE"), "status": "MATCHED"},
        "condition_checks": conditions, "review_condition_checks": [],
        "applicability": "APPLICABLE", "applicability_basis": "ADVERTISEMENT_EVIDENCE",
        "applicability_evidence_ids": ids, "applicability_evidence_line_refs": refs,
        "applicability_metadata_fields": [], "verdict": verdict,
        "evidence_ids": ids, "evidence_line_refs": refs, "requirement_checks": checks,
        "reason": details, "confidence": "HIGH", "needs_researcher_review": bool(mismatch),
    }


def _not_applicable(rule: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    conditions = [{
        "condition_ref": condition["condition_id"], "status": "NOT_SATISFIED",
        "evidence_ids": [], "evidence_line_refs": [],
    } for condition in contract.get("applicability_conditions") or []]
    return {
        "item_id": rule["item_id"],
        "scope_check": {"scope_ref": contract.get("scope_ref", "SCOPE"), "status": "NOT_MATCHED"},
        "condition_checks": conditions, "review_condition_checks": [],
        "applicability": "NOT_APPLICABLE", "applicability_basis": "NOT_APPLICABLE",
        "applicability_evidence_ids": [], "applicability_evidence_line_refs": [],
        "applicability_metadata_fields": [], "verdict": "NOT_APPLICABLE",
        "evidence_ids": [], "evidence_line_refs": [], "requirement_checks": [],
        "reason": "광고에 검산할 합계·비율·기간 계산 관계가 표시되지 않았습니다.",
        "confidence": "HIGH", "needs_researcher_review": False,
    }


def _undetermined(
    rule: dict[str, Any], contract: dict[str, Any], ids: list[str], refs: list[str],
    reason: str, *, matched: bool = False,
) -> dict[str, Any]:
    conditions = []
    for index, condition in enumerate(contract.get("applicability_conditions") or []):
        conditions.append({
            "condition_ref": condition["condition_id"],
            "status": "SATISFIED" if matched and index == 0 else "UNDETERMINED",
            "evidence_ids": ids, "evidence_line_refs": refs,
        })
    return {
        "item_id": rule["item_id"],
        "scope_check": {
            "scope_ref": contract.get("scope_ref", "SCOPE"),
            "status": "MATCHED" if matched else "UNDETERMINED",
        },
        "condition_checks": conditions, "review_condition_checks": [],
        "applicability": "UNDETERMINED", "applicability_basis": "UNDETERMINED",
        "applicability_evidence_ids": ids, "applicability_evidence_line_refs": refs,
        "applicability_metadata_fields": [], "verdict": "UNDETERMINED",
        "evidence_ids": ids, "evidence_line_refs": refs, "requirement_checks": [],
        "reason": reason, "confidence": "LOW", "needs_researcher_review": True,
    }
