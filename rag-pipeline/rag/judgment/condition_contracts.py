"""Source-bound applicability contracts for every operational rule.

The contract never invents a condition from an advertisement or an answer
key.  It preserves the complete authoritative scope wording and gives every
explicit, separately maintained applicability condition a stable ID.  The
judgment validator can therefore reject a verdict which skipped scope or one
of those conditions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


VERSION = "rule-applicability-contract-v2"


def _texts(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def _condition_rows(values: Iterable[str], prefix: str) -> list[dict[str, str]]:
    return [
        {
            "condition_id": f"{prefix}{index}",
            "text": text,
            "source": "authoritative_rule_or_bound_guide",
        }
        for index, text in enumerate(_texts(values), 1)
    ]


def compile_condition_contract(rule: dict[str, Any]) -> dict[str, Any]:
    """Compile one lossless, auditable condition contract.

    ``scope_text`` is deliberately not split with Korean conjunction or
    keyword heuristics.  It is the complete source question and criterion;
    the model must confirm every target/situation/media qualifier in it before
    returning APPLICABLE.  Separately authored applicability conditions are
    enumerated so none can disappear in a free-form reason.
    """
    question = str(rule.get("question") or rule.get("title") or "").strip()
    criterion = str(rule.get("criterion") or "").strip()
    if not criterion and rule.get("source_sheet") == "HWPX_TEMPLATE":
        criterion = "; ".join(_texts([
            f"템플릿 구분={rule.get('title') or question}",
            f"필수여부={rule.get('template_required') or '미기재'}",
            rule.get("guide"),
        ]))
    if not question or not criterion:
        raise ValueError(
            f"{rule.get('item_id')}: condition contract requires question and criterion"
        )

    guide_conditions = _texts(
        condition
        for guide in (rule.get("decision_guides") or [])
        if isinstance(guide, dict)
        for condition in (guide.get("applicability_conditions") or [])
    )
    template_required = str(rule.get("template_required") or "").strip()
    if template_required in {"△", "CONDITIONAL"}:
        # The template's own guidance is the authoritative condition source.
        # If it is blank, retain the full criterion rather than inventing one.
        guide_conditions.extend(
            _texts([rule.get("guide"), rule.get("standard_guidance"), criterion])
        )

    review_conditions = _texts(
        condition
        for guide in (rule.get("decision_guides") or [])
        if isinstance(guide, dict)
        for condition in (guide.get("review_conditions") or [])
    )
    # Source notes can narrow a broad criterion (e.g. umbrella checks). They
    # are not optional commentary and must survive compact prompt projection.
    source_note = str(rule.get("v2_note") or "").strip()
    obligations = [{"obligation_id": "O1", "text": criterion, "source": "criterion"}]
    seen_requirements = {criterion}
    for guide in rule.get("decision_guides") or []:
        if not isinstance(guide, dict):
            continue
        requirements = guide.get("requirements") or []
        if not isinstance(requirements, list) or any(not isinstance(text, str) for text in requirements):
            raise ValueError("bound guide requirements must be a string array")
        for text in _texts(requirements):
            if text in seen_requirements:
                continue
            seen_requirements.add(text)
            obligations.append({"obligation_id": f"O{len(obligations) + 1}", "text": text,
                "source": "bound_guide.requirements", "guide_id": guide.get("guide_id")})
    source_fields = {
        "title": str(rule.get("title") or "").strip(),
        "question": question,
        "criterion": criterion,
        "v2_note": source_note,
        "obligation_checks": obligations,
    }
    source_bytes = json.dumps(
        source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    conditions = _condition_rows(guide_conditions, "A")
    contract = {
        "schema_version": VERSION,
        "scope_ref": "SCOPE",
        "scope_text": "\n".join(_texts([question, criterion, source_note])),
        "source_note": source_note,
        "scope_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "scope_policy": (
            "MATCHED only when every person, product, situation, medium and procedure "
            "qualifier in scope_text applies to the same cited advertisement context"
        ),
        "product_groups": list(rule.get("product_groups") or []),
        "product_subtype": rule.get("product_subtype"),
        "applicability_mode": (
            "CONDITIONAL" if conditions
            else "UNCONDITIONAL"
            if rule.get("source_sheet") == "HWPX_TEMPLATE"
            and template_required in {"O", "REQUIRED"}
            else "SOURCE_SCOPED"
        ),
        "applicability_conditions": conditions,
        "review_conditions": _condition_rows(review_conditions, "U"),
        "obligation": {
            "obligation_id": "O1",
            "text": criterion,
            "source": "criterion",
        },
        "obligation_checks": obligations,
        "obligation_policy": (
            "Check each source O reference separately after passing the gates. "
            "O1 retains the whole criterion including its exceptions and alternative methods. "
            "Do not turn illustrative examples or other products' obligations into mandatory elements. "
            "A compound source paragraph is not a certified atomic checklist; do not claim "
            "all elements are verified when applicability or evidence for any required element is unknown."
        ),
        "obligation_structure": "SOURCE_PLUS_EXPLICIT_REQUIREMENTS" if len(obligations) > 1 else "SOURCE_TEXT_ONLY",
        "unknown_policy": "UNDETERMINED",
    }
    return contract


def attach_condition_contracts(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for rule in rules:
        rule["condition_contract"] = compile_condition_contract(rule)
    return rules


def rule_view_from_v2_item(item: dict[str, Any]) -> dict[str, Any]:
    """Project a raw v2 workbook item without changing its decision text."""
    return {
        "item_id": item.get("id"),
        "source_sheet": "실행_점검항목",
        "title": item.get("title"),
        "question": item.get("question"),
        "criterion": item.get("criterion"),
        "v2_note": item.get("비고") or "",
        "product_groups": list(item.get("적용상품") or []),
        "product_subtype": item.get("세부상품") or None,
        "template_required": item.get("템플릿필수") or None,
        "guide": item.get("기재요령") or None,
        "standard_guidance": item.get("기재요령") or None,
        "decision_guides": [],
    }


def audit_v2_source_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile every source row so omitted runtime scopes fail before inference."""
    contracts: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in contracts:
            raise ValueError(f"invalid or duplicate v2 item_id: {item_id!r}")
        contracts[item_id] = compile_condition_contract(rule_view_from_v2_item(item))
    return {
        "schema_version": VERSION,
        "source_rule_count": len(items),
        "compiled_rule_count": len(contracts),
        "missing_scope_count": sum(
            not str(contract.get("scope_text") or "").strip()
            for contract in contracts.values()
        ),
        "mode_counts": {
            mode: sum(
                contract.get("applicability_mode") == mode
                for contract in contracts.values()
            )
            for mode in ("UNCONDITIONAL", "SOURCE_SCOPED", "CONDITIONAL")
        },
        "contracts": contracts,
    }
