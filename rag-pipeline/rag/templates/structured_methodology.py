"""Compile extracted review-methodology rows without reading customer originals.

This module is deliberately upstream of the operational runner.  It turns the
lossless JSON extracts into an auditable rule-design artifact, but does not
activate the rows for retrieval or judgment.  Advertisement transcriptions and
case-answer rows are rejected.  The only answer-document input allowed is the
explicitly approved first-page retirement scope note, which becomes a scope
policy rather than an item-level judgment rule.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "structured-review-methodology-v1"
SOURCE_TYPE_METHODOLOGY = "CUSTOMER_REVIEW_METHODOLOGY"
SOURCE_TYPE_ASSOCIATION_GUIDANCE = "ASSOCIATION_GUIDANCE"
SOURCE_TYPE_SCOPE_METADATA = "CUSTOMER_SCOPE_METADATA"

FIELD_EXAMPLE = "예 시 문 구"
FIELD_APPROPRIATE = "적정 판단"
FIELD_INAPPROPRIATE = "부적정 / 부적정 판단"
FIELD_INAPPROPRIATE_GUIDE = "부적정 / 안내문구"
FIELD_REVIEW = "확인필요 / 확인필요 판단"
FIELD_REVIEW_GUIDE = "확인필요 / 안내문구"


SOURCE_SPECS = (
    {
        "relative_path": "01_대출성상품-상품명노출/1. 대출성상품-상품명 노출(심의방법) (1).json",
        "rule_prefix": "LOAN-NAMED",
        "template_section": "대출성상품-상품명 노출",
        "template_role": "PRIMARY",
    },
    {
        "relative_path": "02_예금성상품-입출식/12. 예금성상품-입출식 심의방법.json",
        "rule_prefix": "DEPOSIT-DEMAND",
        "template_section": "예금성상품-입출식",
        "template_role": "PRIMARY",
    },
    {
        "relative_path": "03_투자성상품-심의사례/8. 투자성상품-퇴직연금 심의방법.json",
        "rule_prefix": "RETIREMENT",
        "template_section": "투자성상품-퇴직연금 일반",
        "template_role": "RETIREMENT_BASE",
    },
    {
        "relative_path": "03_투자성상품-심의사례/10. 투자성상품-ETF 심의방법.json",
        "rule_prefix": "RETIREMENT-ETF",
        "template_section": "투자성상품-ETF",
        "template_role": "RETIREMENT_ADD_ON",
    },
    {
        "relative_path": "03_투자성상품-심의사례/11. 투자성상품-ELB 심의방법.json",
        "rule_prefix": "RETIREMENT-ELB",
        "template_section": "투자성상품-ELB",
        "template_role": "RETIREMENT_ADD_ON",
    },
)

RETIREMENT_SCOPE_RELATIVE_PATH = (
    "03_투자성상품-심의사례/8. 투자성상품-퇴직연금(심의정답).md"
)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_index(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("source extract manifest must be a list")
    return {(row["group"], row["name"]): row for row in rows}


def _verify_extract(root: Path, relative_path: str, manifest: dict) -> tuple[Path, dict]:
    path = root / Path(relative_path)
    if not path.is_file():
        raise ValueError(f"required source extract missing: {relative_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    key = (meta.get("group"), meta.get("name"))
    manifest_row = manifest.get(key)
    if not manifest_row:
        raise ValueError(f"source extract absent from manifest: {relative_path}")
    if meta.get("sha256") != manifest_row.get("sha256"):
        raise ValueError(f"source hash differs from manifest: {relative_path}")
    if data.get("kind") != "xlsx":
        raise ValueError(f"methodology extract must be xlsx JSON: {relative_path}")
    return path, data


def _structured_rows(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for sheet in data.get("sheets", []):
        structured = sheet.get("structured") or {}
        for row in structured.get("records", []):
            rows.append((_text(sheet.get("title")), row))
    if not rows:
        raise ValueError(f"no structured methodology rows: {data.get('meta', {}).get('name')}")
    return rows


def _source_fragments(row: dict[str, Any]) -> list[dict[str, str]]:
    """Keep condition-bearing source text without pretending to parse its truth value."""
    fragments = []
    for field in (FIELD_APPROPRIATE, FIELD_INAPPROPRIATE, FIELD_REVIEW):
        value = _text(row.get(field))
        if value and any(token in value for token in ("경우", "언급", "포함", "사용", "활용", "단,")):
            fragments.append({"source_field": field, "text": value})
    return fragments


def _leading_applicability_triggers(row: dict[str, Any]) -> list[dict[str, str]]:
    """Extract only source-authored antecedents that gate the whole row.

    Reviewer/remediation guidance commonly has the form ``X인 경우, Y를
    기재``.  ``X`` is an applicability fact and ``Y`` is the obligation.  By
    contrast, outcome text such as ``안내문구 언급 없는 경우`` describes a
    missing obligation and must not become its own applicability trigger.
    Restricting this extraction to a leading clause in guidance fields keeps
    those two roles separate and does not infer conditions from examples.
    """
    triggers: list[dict[str, str]] = []
    for field in (FIELD_INAPPROPRIATE_GUIDE, FIELD_REVIEW_GUIDE):
        value = _text(row.get(field))
        if not value:
            continue
        match = re.match(r"^\s*(.+?(?:경우|\s시))\s*[,，]", value)
        if not match:
            continue
        predicate = match.group(1).strip()
        if not predicate:
            continue
        triggers.append({
            "trigger_id": f"T{len(triggers) + 1}",
            "source_field": field,
            "predicate_text": predicate,
            "source_text": value,
            "gate_type": "TRIGGER",
            "evaluator": "STRUCTURED_METADATA_OR_LLM_FACT_EXTRACTION",
            "allowed_states": ["TRUE", "FALSE", "UNKNOWN"],
        })
    return triggers


def _exceptions(row: dict[str, Any]) -> list[dict[str, str]]:
    exceptions = []
    for field in (FIELD_APPROPRIATE, FIELD_INAPPROPRIATE, FIELD_REVIEW):
        value = _text(row.get(field))
        if value and any(token in value for token in ("단,", "누락되어도 적정", "생략 가능", "부적정 판단하지 않음")):
            exceptions.append({"source_field": field, "text": value})
    return exceptions


def _atomic_checks(row: dict[str, Any]) -> list[dict[str, str]]:
    checks = []
    for field in (FIELD_APPROPRIATE, FIELD_INAPPROPRIATE, FIELD_INAPPROPRIATE_GUIDE):
        value = _text(row.get(field))
        numbered = list(re.finditer(r"([①②③④⑤⑥⑦⑧⑨])\s*([^①②③④⑤⑥⑦⑧⑨]+)", value))
        for match in numbered:
            checks.append({
                "check_id": match.group(1),
                "source_field": field,
                "text": match.group(2).strip(),
            })
    return checks


def _dependencies(row: dict[str, Any]) -> list[str]:
    values = "\n".join(_text(value) for value in row.values())
    return sorted(set(re.findall(r"\b[A-H][1-9][0-9]*셀?", values)))


def _decision_route(row: dict[str, Any]) -> str:
    values = "\n".join(_text(value) for value in row.values())
    if "한줄에 2개 이상" in values or "줄바꿈없이" in values:
        return "RULE_LINE_STRUCTURE_AND_LLM_MEANING"
    if any(token in values for token in ("≠", "≤", "=", "한 달 이내", "합인 경우", "산식")):
        return "RULE_COMPARISON_WITH_LLM_EXTRACTION"
    if any(token in values for token in ("로고", "색상", "글자크기", "시인성")):
        return "HUMAN_VISUAL_REVIEW_WITH_TEXT_FACET"
    return "LLM_WITH_SOURCE_GATES"


def _query_fragment(role: str, source_field: str, text: str) -> dict[str, Any]:
    return {
        "role": role,
        "source_field": source_field,
        "text": text,
        "exact_match_required": False,
        "can_serve_as_advertisement_evidence": False,
    }


def _retrieval_plan(row: dict[str, Any]) -> dict[str, Any]:
    """Separate rule-side search hints from advertisement-side evidence.

    Methodology examples and reviewer guidance can improve semantic retrieval,
    but their presence in the rule source can never prove that an advertisement
    contains the required statement or prohibited expression.
    """
    groups: dict[str, list[dict[str, Any]]] = {
        "obligation_concept": [],
        "positive_semantic_examples": [],
        "satisfied_criteria": [],
        "violation_criteria": [],
        "review_criteria": [],
    }
    fields = (
        ("obligation_concept", "RULE_LABEL", "구분"),
        ("positive_semantic_examples", "POSITIVE_EXAMPLE", FIELD_EXAMPLE),
        ("satisfied_criteria", "SATISFIED_CRITERION", FIELD_APPROPRIATE),
        ("violation_criteria", "VIOLATION_CRITERION", FIELD_INAPPROPRIATE),
        ("violation_criteria", "REMEDIATION_GUIDANCE", FIELD_INAPPROPRIATE_GUIDE),
        ("review_criteria", "REVIEW_TRIGGER", FIELD_REVIEW),
        ("review_criteria", "REVIEW_GUIDANCE", FIELD_REVIEW_GUIDE),
    )
    for group, role, field in fields:
        value = _text(row.get(field))
        if value:
            groups[group].append(_query_fragment(role, field, value))
    return {
        "query_groups": groups,
        "query_combination": "ROLE_AWARE_SEMANTIC_RETRIEVAL",
        "template_text_is_evidence": False,
        "outcome_requires_advertisement_evidence": True,
        "absence_requires_complete_advertisement_scan": True,
    }


def _compile_row(spec: dict[str, str], data: dict, sheet: str, row: dict[str, Any]) -> dict:
    excel_row = int(row["excel_row"])
    inappropriate = _text(row.get(FIELD_INAPPROPRIATE))
    review = _text(row.get(FIELD_REVIEW))
    source_types = [SOURCE_TYPE_METHODOLOGY]
    joined = "\n".join(_text(value) for value in row.values())
    if "은행연합회 지도사항" in joined:
        source_types.append(SOURCE_TYPE_ASSOCIATION_GUIDANCE)
    issues = []
    if spec["rule_prefix"] != "LOAN-NAMED" and "대출 유의사항" in joined:
        issues.append("SOURCE_SCOPE_TERM_CONFLICT")
    applicability_triggers = _leading_applicability_triggers(row)
    return {
        "rule_id": f"MTH-{spec['rule_prefix']}-R{excel_row:02d}",
        "template_section": spec["template_section"],
        "template_role": spec["template_role"],
        "label": _text(row.get("구분")),
        "display_example": _text(row.get(FIELD_EXAMPLE)),
        "example_policy": "SEMANTIC_RETRIEVAL_HINT_NOT_AN_EXACT_MATCH_OR_EVIDENCE",
        "source": {
            "filename": data["meta"]["name"],
            "original_sha256": data["meta"]["sha256"],
            "sheet": sheet,
            "excel_row": excel_row,
        },
        "source_types": source_types,
        "applicability": {
            "logic": "SOURCE_TEXT_ONLY",
            "criteria": _source_fragments(row),
            "triggers": applicability_triggers,
            "default": (
                "SELECTED_TEMPLATE"
                if not applicability_triggers
                else "EVALUATE_TRIGGERS_BEFORE_OBLIGATIONS"
            ),
            "unknown_policy": "UNDETERMINED_NOT_INAPPLICABLE",
        },
        "exceptions": _exceptions(row),
        "obligation": {
            "logic": "ALL_EXPLICIT_CHECKS",
            "label": _text(row.get("구분")),
            "atomic_checks": _atomic_checks(row),
            "source_fields": [FIELD_APPROPRIATE, FIELD_INAPPROPRIATE, FIELD_REVIEW],
        },
        "retrieval": _retrieval_plan(row),
        "outcomes": {
            "satisfied_when": _text(row.get(FIELD_APPROPRIATE)),
            "violated_when": None if "부적정 판단하지 않음" in inappropriate else inappropriate,
            "violation_guidance": _text(row.get(FIELD_INAPPROPRIATE_GUIDE)),
            "review_when": review or None,
            "review_guidance": _text(row.get(FIELD_REVIEW_GUIDE)) or None,
        },
        "source_cell_dependencies": _dependencies(row),
        "decision_route": _decision_route(row),
        "issues": issues,
        "activation_status": (
            "SOURCE_REVIEW_REQUIRED" if issues else "STRUCTURED_NOT_OPERATIONALLY_CONNECTED"
        ),
    }


def _retirement_scope_policy(root: Path) -> dict[str, Any]:
    path = root / RETIREMENT_SCOPE_RELATIVE_PATH
    if not path.is_file():
        raise ValueError("retirement scope-note extract missing")
    text = path.read_text(encoding="utf-8")
    match = re.search(r"### p\.1\s+```text\s*(.*?)\s*```", text, re.DOTALL)
    if not match:
        raise ValueError("retirement page-1 scope note not found")
    page_one = match.group(1)
    required = (
        "금융투자상품이 언급된 경우",
        "로고 병기 의무는",
        "펀드 단독 광고용 템플릿을 별도로 제작",
    )
    if any(anchor not in page_one for anchor in required):
        raise ValueError("retirement scope note does not match approved page-1 anchors")
    return {
        "policy_id": "SCOPE-RETIREMENT-INSTRUMENT-COMPOSITION",
        "source_type": SOURCE_TYPE_SCOPE_METADATA,
        "source": {
            "relative_path": RETIREMENT_SCOPE_RELATIVE_PATH,
            "extract_sha256": _file_sha256(path),
            "allowed_section": "p.1",
            "case_answer_rows_loaded": False,
        },
        "base_template": "투자성상품-퇴직연금 일반",
        "composition": {
            "logic": "ALL_APPLICABLE",
            "when_financial_instrument_is_mentioned": [
                "RETIREMENT_BASE",
                "MATCHING_RETIREMENT_INSTRUMENT_ADD_ON",
            ],
            "instrument_add_ons": {
                "펀드": "투자성상품-퇴직연금(IRP) 펀드상품 노출",
                "ETF": "투자성상품-ETF",
                "ELB": "투자성상품-ELB",
            },
        },
        "deposit_protection_logo": {
            "required": False,
            "scope": "RETIREMENT_COMPOSITE_ADVERTISEMENT",
            "reason": "퇴직연금은 예금자보호 상품으로도 운용 가능하며 기본·추가 유의사항을 함께 적용",
            "does_not_change_text_disclosure_rules": True,
        },
        "standalone_scope": {
            "fund": "SEPARATE_TEMPLATE_REQUIRED_NOT_AVAILABLE",
            "etf": "RETIREMENT_ADD_ON_ONLY",
            "elb": "RETIREMENT_ADD_ON_ONLY",
        },
        "activation_status": "STRUCTURED_NOT_OPERATIONALLY_CONNECTED",
    }


def compile_extracted_methodologies(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = _manifest_index(root)
    rules = []
    sources = []
    for spec in SOURCE_SPECS:
        path, data = _verify_extract(root, spec["relative_path"], manifest)
        source_rows = _structured_rows(data)
        sources.append({
            "relative_path": spec["relative_path"],
            "extract_sha256": _file_sha256(path),
            "original_sha256": data["meta"]["sha256"],
            "structured_row_count": len(source_rows),
        })
        rules.extend(_compile_row(spec, data, sheet, row) for sheet, row in source_rows)

    ids = [row["rule_id"] for row in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate structured methodology rule id")
    line_members = [
        row["rule_id"] for row in rules
        if row["template_section"] == "대출성상품-상품명 노출"
        and "은행연합회 지도사항" in "\n".join(
            value or "" for value in row["outcomes"].values()
        )
    ]
    shared_rules = [{
        "rule_id": "MTH-LOAN-NAMED-SHARED-LINE-SEPARATION",
        "source_type": SOURCE_TYPE_ASSOCIATION_GUIDANCE,
        "member_rule_ids": line_members,
        "applicability": "TWO_OR_MORE_DISTINCT_LOAN_NOTICES_ARE_PRESENT",
        "obligation": "각 대출 유의사항을 서로 다른 렌더링 줄로 구분",
        "violation": "동일한 렌더링 줄에 서로 다른 대출 유의사항 두 개 이상을 줄바꿈 없이 나열",
        "required_input": "VERIFIED_RENDERED_LINE_STRUCTURE",
        "decision_route": "RULE_LINE_STRUCTURE",
        "activation_status": "STRUCTURED_NOT_OPERATIONALLY_CONNECTED",
    }]
    association_rows = [
        row for row in rules if SOURCE_TYPE_ASSOCIATION_GUIDANCE in row["source_types"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_root": str(root),
        "policy": {
            "advertisements_loaded": False,
            "case_answer_judgments_loaded": False,
            "examples_are_conditions": False,
            "operationally_connected": False,
        },
        "sources": sources,
        "rules": rules,
        "shared_rules": shared_rules,
        "scope_policies": [_retirement_scope_policy(root)],
        "legal_reference_audit": {
            "financial_consumer_protection_act_article_19": "EXISTING_CORPUS_REFERENCE",
            "retirement_pension_supervision_regulation_article_16_2": {
                "status": "FOUND_IN_V2_AS_D-194_R-0554",
                "methodology_source": False,
                "rule_role": "CONDITIONAL_PROHIBITION_REQUIRING_SEPARATE_ACTIVATION_REVIEW",
            },
            "bank_federation_guidance": {
                "evidence_type": "GUIDELINE",
                "source_subtype": SOURCE_TYPE_ASSOCIATION_GUIDANCE,
                "article_number": None,
            },
        },
        "counts": {
            "methodology_rules": len(rules),
            "shared_rules": len(shared_rules),
            "scope_policies": 1,
            "association_guidance_rows": len(association_rows),
            "loan_line_guidance_rows": len(line_members),
            "source_review_required": sum(
                row["activation_status"] == "SOURCE_REVIEW_REQUIRED" for row in rules
            ),
        },
    }


def write_compiled_methodologies(root: Path, output: Path) -> dict[str, Any]:
    document = compile_extracted_methodologies(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return document
