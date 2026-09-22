"""Conservative execution routing for template and supplemental review rules.

The compiler assigns work by source-language capability.  It never turns an
example into an exact-match duty and never treats rule-side text as evidence
from the advertisement.  Every non-empty source field is retained in the
clause ledger; unresolved meaning blocks automatic activation instead of being
silently dropped.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable


SCHEMA_VERSION = "complete-rule-routing-v1"
EMPTY_VALUES = {"", "-", "없음", "해당 없음"}
CONDITION_MARKERS = ("경우", "언급", "있는 상품", "활용 시", "포함 시", "광고 시", "일 때")
EXCEPTION_MARKERS = ("단,", "생략 가능", "누락되어도", "제한 없는 경우", "제외", "면제")
VISUAL_MARKERS = (
    "볼드", "색상", "글자크기", "글자 크기", "시인성", "배경", "로고", "동일 화면",
    "첫 페이지", "위치", "구별", "강조", "크기", "배치",
)
CALCULATION_MARKERS = (
    "≤", "≥", "=", "산식", "합계", "합인", "계산", "30일", "한 달", "기준일",
    "세전", "세후", "최대", "최소", "최저", "최고", "기간", "단위", "반올림",
)
FORMAT_MARKERS = ("형식", "첫머리", "머리말", "심의필", "심의번호", "유효기간", "연락처")
SEMANTIC_MARKERS = (
    "취지", "설명", "유사", "오인", "명확", "의미", "연관", "객관", "중요", "위험",
    "보장", "손실", "혜택", "수익", "비용", "상품", "대가", "후기", "절세",
)
EXPLICIT_APPLICABILITY_PATTERNS = (
    "광고물 내", "활용 시 필수", "있는 상품 필수", "세제혜택 포함 시 필수",
    "텍스트만 입력 가능한", "면적 제한 시", "제한 없는 경우 생략 가능",
    "앱/웹", "LMS 등",
)


def _text(value: Any) -> str:
    value = str(value or "").strip()
    return "" if value in EMPTY_VALUES else value


def _contains(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


def _source_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _clause_ledger(fields: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = []
    for field, raw in fields.items():
        text = _text(raw)
        if not text:
            continue
        roles = []
        if field == "example":
            roles.append("SEMANTIC_RETRIEVAL_HINT")
        elif field == "satisfied":
            roles.append("SATISFIED_CRITERION")
        elif field == "violated":
            roles.append("VIOLATION_CRITERION")
        elif field == "review":
            roles.append("REVIEW_TRIGGER")
        elif field.endswith("guidance"):
            roles.append("REMEDIATION_OR_REVIEW_GUIDANCE")
        else:
            roles.append("RULE_LABEL_OR_SCOPE")
        if field != "example" and _contains(text, CONDITION_MARKERS):
            roles.append("CONDITIONAL_OUTCOME_BRANCH")
        ledger.append({
            "clause_id": f"S{len(ledger) + 1}",
            "source_field": field,
            "text": text,
            "roles": roles,
            "exact_match_required": False,
            "can_serve_as_advertisement_evidence": False,
        })
    return ledger


def _engine_plan(
    text: str, *, has_external_slots: bool = False, force_semantic: bool = False
) -> dict[str, Any]:
    visual = _contains(text, VISUAL_MARKERS)
    calculation = _contains(text, CALCULATION_MARKERS)
    format_check = _contains(text, FORMAT_MARKERS)
    semantic = force_semantic or _contains(text, SEMANTIC_MARKERS) or not (calculation or format_check)
    owners = ["RULE_APPLICABILITY_3VL"]
    if calculation or format_check:
        owners.append("RULE_DETERMINISTIC_CHECK")
    if semantic:
        owners.append("LLM_SEMANTIC_JUDGMENT")
    if visual:
        owners.append("HUMAN_VISUAL_REVIEW")
    if has_external_slots:
        owners.append("EXTERNAL_INPUT_GATE")
    if visual:
        route = "HYBRID_WITH_HUMAN_REVIEW" if len(owners) > 2 else "HUMAN_VISUAL_REVIEW"
    elif "RULE_DETERMINISTIC_CHECK" in owners and "LLM_SEMANTIC_JUDGMENT" in owners:
        route = "HYBRID_RULE_LLM"
    elif "RULE_DETERMINISTIC_CHECK" in owners:
        route = "RULE_ENGINE"
    else:
        route = "LLM_WITH_RULE_GATES"
    return {
        "route": route,
        "owners": owners,
        "rule_responsibility": (
            "상품·업무·매체·상황 조건과 예외를 3값으로 계산하고, 구조화된 수치·날짜·형식만 비교"
        ),
        "llm_responsibility": (
            "광고 원문의 의미 동등성·대상 연결을 판단하고 직접 인용을 반환; 조건·계산 결과 변경 금지"
        ) if "LLM_SEMANTIC_JUDGMENT" in owners else None,
        "human_responsibility": (
            "원본 렌더링의 색상·크기·배치·대비를 판정"
        ) if visual else None,
    }


def _gate_specs(ledger: list[dict[str, Any]], role: str, gate_type: str) -> list[dict[str, Any]]:
    gates = []
    for entry in ledger:
        if role not in entry["roles"]:
            continue
        text = entry["text"]
        if _contains(text, VISUAL_MARKERS):
            evaluator = "HUMAN_SOURCE_FACT"
        elif _contains(text, ("LMS", "MMS", "앱/웹", "온라인", "광고물 내", "언급")):
            evaluator = "STRUCTURED_METADATA_OR_LLM_FACT_EXTRACTION"
        else:
            evaluator = "LLM_FACT_EXTRACTION_THEN_RULE_3VL"
        gates.append({
            "gate_id": f"{gate_type[0]}{len(gates) + 1}",
            "source_clause_ref": entry["clause_id"],
            "predicate_text": text,
            "gate_type": gate_type,
            "evaluator": evaluator,
            "allowed_states": ["TRUE", "FALSE", "UNKNOWN"],
        })
    return gates


def compile_template_item(
    row: dict[str, Any], *, latest_methodology: dict[str, Any] | None = None
) -> dict[str, Any]:
    fields = {
        "label": row.get("구분"),
        "example": row.get("예시문구"),
        "satisfied": row.get("적정판단 / 필수여부"),
        "violated": row.get("부적정판단 / 기재요령"),
        "violation_guidance": row.get("부적정 안내문구"),
        "review": row.get("확인필요 판단"),
        "review_guidance": row.get("확인필요 안내문구"),
    }
    source_precedence = "INTEGRATED_TEMPLATE_273"
    if latest_methodology:
        fields.update({
            "label": latest_methodology.get("label"),
            "example": latest_methodology.get("display_example"),
            "satisfied": latest_methodology.get("outcomes", {}).get("satisfied_when"),
            "violated": latest_methodology.get("outcomes", {}).get("violated_when"),
            "violation_guidance": latest_methodology.get("outcomes", {}).get("violation_guidance"),
            "review": latest_methodology.get("outcomes", {}).get("review_when"),
            "review_guidance": latest_methodology.get("outcomes", {}).get("review_guidance"),
        })
        source_precedence = "LATEST_EXTRACTED_METHODOLOGY_OVERRIDE"
    ledger = _clause_ledger(fields)
    conditional_template = "△" in _text(fields["satisfied"])
    for entry in ledger:
        text = entry["text"]
        if entry["source_field"] == "example":
            continue
        explicit_scope = _contains(text, EXPLICIT_APPLICABILITY_PATTERNS)
        conditional_guide = conditional_template and entry["source_field"] in {
            "violated", "violation_guidance", "review", "review_guidance"
        }
        if explicit_scope or conditional_guide:
            entry["roles"].append("APPLICABILITY_CONDITION")
        if (explicit_scope or conditional_guide) and _contains(text, EXCEPTION_MARKERS):
            entry["roles"].append("EXCEPTION")
    all_text = "\n".join(entry["text"] for entry in ledger)
    conditions = _gate_specs(ledger, "APPLICABILITY_CONDITION", "TRIGGER")
    exceptions = _gate_specs(ledger, "EXCEPTION", "EXCEPTION")
    review = [entry["clause_id"] for entry in ledger if "REVIEW_TRIGGER" in entry["roles"]]
    example = _text(fields["example"])
    force_semantic = (
        _text(fields["satisfied"]) in {"필수(O)", "필수(△)"}
        and len(example) >= 25
        and _text(fields["label"]) != "심의번호"
    )
    engine = _engine_plan(all_text, force_semantic=force_semantic)
    unresolved = []
    if engine["route"] == "HYBRID_WITH_HUMAN_REVIEW":
        unresolved.append("VISUAL_FACET_REQUIRES_HUMAN")
    return {
        "rule_id": f"TPL-MAP-{int(row['번호']):03d}",
        "source_kind": "TEMPLATE",
        "source_precedence": source_precedence,
        "product_template": _text(row.get("상품유형")),
        "label": _text(fields["label"]),
        "source_fields": fields,
        "source_field_sha256": _source_hash(fields),
        "clause_ledger": ledger,
        "applicability": {
            "logic": "ALL(TEMPLATE_SELECTED, TRIGGERS_TRUE_OR_UNKNOWN_BLOCKED, NO_EXCEPTION_TRUE)",
            "triggers": conditions,
            "exceptions": exceptions,
            "evaluation_order": ["TEMPLATE_SELECTED", "TRIGGERS", "EXCEPTIONS", "OBLIGATIONS"],
            "unknown_policy": "UNDETERMINED_NOT_INAPPLICABLE",
        },
        "obligation": {
            "logic": "ALL_EXPLICIT_SOURCE_REQUIREMENTS",
            "satisfied_source": "satisfied",
            "violation_source": "violated",
            "review_source": "review",
            "example_policy": "SEMANTIC_HINT_NOT_EXACT_MATCH_OR_EVIDENCE",
            "branch_conditions": [
                {
                    "source_clause_ref": entry["clause_id"],
                    "predicate_text": entry["text"],
                    "unknown_policy": "OBLIGATION_UNDETERMINED",
                }
                for entry in ledger
                if "CONDITIONAL_OUTCOME_BRANCH" in entry["roles"]
            ],
        },
        "decision": engine,
        "review_clause_refs": review,
        "evidence_contract": {
            "rule_text_is_evidence": False,
            "advertisement_direct_quote_required": True,
            "absence_requires_complete_scan": True,
            "same_product_scenario_required": True,
        },
        "legal_basis": {
            "statute": _text(row.get("근거(법령)")),
            "association": _text(row.get("근거(협회 규정)")),
            "display_only_not_new_obligation": True,
        },
        "unresolved": unresolved,
        "clause_coverage": {
            "nonempty_source_field_count": len(ledger),
            "ledger_clause_count": len(ledger),
            "all_nonempty_fields_preserved": True,
            "semantic_atomization_claimed": False,
        },
        "release_state": "STRUCTURED_NOT_OPERATIONALLY_CONNECTED",
    }


def compile_supplemental_item(row: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "label": row.get("약칭"),
        "activation": row.get("발동조건 초안"),
        "source": row.get("출처"),
        "criterion": row.get("원문 전체 보존"),
        "exception_or_hold": row.get("예외·사람검토·보류"),
    }
    ledger = _clause_ledger(fields)
    slots = [_text(value) for value in str(row.get("분리할 자료 슬롯") or "").split(";")]
    slots = [value for value in slots if value]
    return {
        "rule_id": _text(row.get("규칙ID")),
        "source_kind": "SUPPLEMENTAL_V2",
        "label": _text(row.get("약칭")),
        "scope_status": _text(row.get("업권 재검토 상태")),
        "source_fields": fields,
        "source_field_sha256": _source_hash(fields),
        "clause_ledger": ledger,
        "applicability": {
            "logic": "ALL(SOURCE_SCOPE, PRODUCT_OR_BUSINESS, MEDIA_OR_CONTENT_TRIGGER, INPUTS_AVAILABLE, NO_EXCEPTION)",
            "trigger_text": _text(row.get("발동조건 초안")),
            "unknown_policy": "DO_NOT_RUN_OR_HUMAN_REVIEW",
        },
        "required_input_slots": slots,
        "obligation": {
            "logic": "SOURCE_TEXT_PENDING_ATOMIC_APPROVAL",
            "criterion": _text(row.get("원문 전체 보존")),
        },
        "decision": {
            "route": "HYBRID_RULE_LLM",
            "owners": ["RULE_APPLICABILITY_3VL", "RULE_DETERMINISTIC_CHECK", "LLM_SEMANTIC_JUDGMENT"],
            "rule_responsibility": _text(row.get("코드 담당(설계)")),
            "llm_responsibility": _text(row.get("LLM 담당(설계)")),
            "human_responsibility": _text(row.get("예외·사람검토·보류")) or None,
        },
        "evidence_contract": {
            "rule_text_is_evidence": False,
            "advertisement_direct_quote_required": True,
            "required_slots_must_share_product_and_version": True,
        },
        "unresolved": ["ATOMIC_CLAUSE_APPROVAL_REQUIRED"],
        "clause_coverage": {
            "nonempty_source_field_count": len(ledger),
            "ledger_clause_count": len(ledger),
            "all_nonempty_fields_preserved": True,
            "semantic_atomization_claimed": False,
        },
        "release_state": "STRUCTURED_NOT_OPERATIONALLY_CONNECTED",
    }


def compile_special_policy(entry: dict[str, Any]) -> dict[str, Any]:
    item_id = _text(entry.get("item_id"))
    human = entry.get("execution_tier") == "HUMAN_VISUAL_REVIEW"
    fields = {"source_fragment": entry.get("source_fragment")}
    return {
        "rule_id": item_id,
        "source_kind": "SUPPLEMENTAL_V2_SPECIAL",
        "label": item_id,
        "source_fields": fields,
        "source_field_sha256": _source_hash(fields),
        "clause_ledger": _clause_ledger(fields),
        "applicability": {
            "logic": "ALL(RETRIEVAL_HIT, SOURCE_FRAGMENT_MATCH, EVIDENCE_TRIGGER_MATCH)",
            "trigger_any": list(entry.get("evidence_trigger_any") or []),
            "unknown_policy": "DO_NOT_AUTO_JUDGE",
        },
        "required_input_slots": ["광고 원문", "원본 렌더링"] if human else ["광고 원문", "상품·표현 문맥"],
        "obligation": {"logic": "SOURCE_FRAGMENT_BOUND", "criterion": _text(entry.get("source_fragment"))},
        "decision": {
            "route": "HUMAN_VISUAL_REVIEW" if human else "HYBRID_RULE_LLM",
            "owners": (["RULE_APPLICABILITY_3VL", "HUMAN_VISUAL_REVIEW"] if human else
                       ["RULE_APPLICABILITY_3VL", "LLM_SEMANTIC_JUDGMENT"]),
            "rule_responsibility": "검색·원문 발동조건과 상품 범위를 계산",
            "llm_responsibility": None if human else "발동 표현의 실제 의미와 예외를 광고 원문에서 판정",
            "human_responsibility": "배경 대비·색상·형태 판정" if human else None,
        },
        "evidence_contract": {"rule_text_is_evidence": False, "advertisement_direct_quote_required": True},
        "unresolved": [],
        "clause_coverage": {
            "nonempty_source_field_count": 1,
            "ledger_clause_count": 1,
            "all_nonempty_fields_preserved": True,
            "semantic_atomization_claimed": True,
        },
        "release_state": "POLICY_REGISTERED_NOT_BULK_ACTIVATED",
    }


def build_complete_routing(
    template_rows: list[dict[str, Any]],
    supplemental_rows: list[dict[str, Any]],
    special_entries: list[dict[str, Any]],
    latest_loan_methodology: list[dict[str, Any]],
) -> dict[str, Any]:
    if (len(template_rows), len(supplemental_rows), len(special_entries)) != (273, 29, 3):
        raise ValueError("complete routing requires exactly 273 template + 29 supplemental + 3 special rows")
    if len(latest_loan_methodology) != 28:
        raise ValueError("latest loan methodology override must contain 28 rows")
    template_rules = []
    for index, row in enumerate(template_rows):
        override = latest_loan_methodology[index] if index < 28 else None
        if override and _text(row.get("구분")).replace("\n", "") != _text(override.get("label")).replace("\n", ""):
            raise ValueError(f"loan override label mismatch at template row {index + 1}")
        template_rules.append(compile_template_item(row, latest_methodology=override))
    supplemental_rules = [compile_supplemental_item(row) for row in supplemental_rows]
    special_rules = [compile_special_policy(entry) for entry in special_entries]
    rules = [*template_rules, *supplemental_rules, *special_rules]
    ids = [rule["rule_id"] for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule IDs in 305-row routing scope")
    route_counts = Counter(rule["decision"]["route"] for rule in rules)
    owner_counts = Counter(owner for rule in rules for owner in rule["decision"]["owners"])
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "PRE_RUNTIME_STRUCTURE_NOT_PREDICTION",
        "physical_item_count": len(rules),
        "counts": {
            "template": len(template_rules),
            "supplemental_retained": len(supplemental_rules),
            "special_conditioned_or_human": len(special_rules),
            "routes": dict(route_counts),
            "owners": dict(owner_counts),
            "latest_loan_overrides": 28,
            "unresolved_items": sum(bool(rule["unresolved"]) for rule in rules),
            "source_fields_dropped": sum(
                not rule["clause_coverage"]["all_nonempty_fields_preserved"] for rule in rules
            ),
        },
        "policies": {
            "conditions_evaluated_before_obligations": True,
            "unknown_condition_blocks_definitive_verdict": True,
            "examples_are_semantic_hints_only": True,
            "rule_text_is_never_advertisement_evidence": True,
            "legal_mapping_does_not_create_an_extra_obligation": True,
            "operationally_connected": False,
        },
        "rules": rules,
    }
