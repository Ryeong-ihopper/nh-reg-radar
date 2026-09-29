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
import re
from typing import Any, Iterable
from rag.judgment.temporal import date_window_clauses
from rag.judgment.source_checks import source_scope_clauses, quoted_required_clauses
from rag.judgment.obligation_logic import (
    validate_applicability_expression,
    validate_expression,
)


VERSION = "rule-applicability-contract-v2"


def _texts(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def _condition_role(text: str) -> str:
    """Classify an authored condition without using advertisement content.

    An unknown trigger can make an obligation inapplicable (for example,
    whether generative AI was used).  An unknown exemption is different: when
    the disclosure is already present, either possible answer is compliant.
    The wrapper sentence mentions exemptions for every conditional template,
    so classification must use only the original guidance after the marker.
    """
    source_text = text.rsplit("기재요령 원문:", 1)[-1]
    if re.search(r"(?:생략\s*가능|생략할\s*수|면제|제외\s*가능)", source_text):
        return "EXEMPTION"
    return "TRIGGER"


def _condition_rows(values: Iterable[str], prefix: str) -> list[dict[str, str]]:
    return [
        {
            "condition_id": f"{prefix}{index}",
            "text": text,
            "source": "authoritative_rule_or_bound_guide",
            "condition_role": _condition_role(text) if prefix == "A" else "REVIEW",
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
    guide_conditions.extend(source_scope_clauses(question))
    template_required = str(rule.get("template_required") or "").strip()
    if template_required in {"△", "CONDITIONAL"}:
        # The template's own guidance is the authoritative condition source.
        # If it is blank, retain the full criterion rather than inventing one.
        template_conditions = _texts([rule.get("guide"), rule.get("standard_guidance")]) or [criterion]
        if rule.get("source_sheet") == "HWPX_TEMPLATE":
            template_conditions = [
                "다음 기재요령에 따라 이 광고에 기재 의무가 적용되는가? "
                "필수 조건과 생략·면제 조건의 방향을 구분한다. "
                "생략·면제가 확인되면 NOT_SATISFIED, 의무 적용이 확인되면 SATISFIED, "
                "어느 쪽인지 확인할 수 없으면 UNDETERMINED. 기재요령 원문: " + text
                for text in template_conditions
            ]
        guide_conditions.extend(template_conditions)

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
    for text in date_window_clauses(criterion) + quoted_required_clauses(criterion):
        if text not in seen_requirements:
            seen_requirements.add(text)
            obligations.append({'obligation_id':f'O{len(obligations)+1}', 'text':text, 'source':'criterion'})
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
    # Only explicit, unconditional source-marked alternatives can be split
    # here. Mixed/conditional source paragraphs retain their complete O1;
    # missing structure never authorizes inventing an atomic checklist.
    basis = rule.get("template_basis") or {}
    members = basis.get("alternative_members") or []
    explicit_alternatives = (
        rule.get("source_sheet") == "HWPX_TEMPLATE"
        and basis.get("alternative_policy") == "ANY_OF"
        and isinstance(members, list) and len(members) > 1
        and not rule.get("decision_guides")
        and not guide_conditions and not review_conditions
        and not basis.get("manual_review_required")
        and all(isinstance(m, dict)
                and m.get("source_sheet") == "HWPX_TEMPLATE"
                and m.get("template_required") in {"O", "REQUIRED"}
                and str(m.get("criterion") or "").strip()
                and str(m.get("source_ref") or "").strip()
                for m in members)
    )
    if explicit_alternatives:
        obligations = []
        methods = []
        for member in members:
            # A method's explicit dates/quoted requirements belong to that
            # method, not to every other allowed alternative.
            texts = _texts([member["criterion"], *date_window_clauses(member["criterion"]),
                            *quoted_required_clauses(member["criterion"])])
            branch = []
            for text in texts:
                obligation_id = f"O{len(obligations) + 1}"
                obligations.append({"obligation_id": obligation_id, "text": text,
                                    "source": "template_alternative", "source_ref": member["source_ref"]})
                branch.append({"ref": obligation_id})
            methods.append(branch[0] if len(branch) == 1 else {"all": branch})
        logic = {"any": methods}
    else:
        logic = {"all": [{"ref": value["obligation_id"]} for value in obligations]}
    validate_expression(logic, [value["obligation_id"] for value in obligations])
    source_fields = {
        "title": str(rule.get("title") or "").strip(),
        "question": question,
        "criterion": criterion,
        "v2_note": source_note,
        "obligation_checks": obligations,
        "obligation_logic": logic,
        "rule_relations": list(rule.get("rule_relations") or []),
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
        "rule_relations": list(rule.get("rule_relations") or []),
        "obligation": {
            "obligation_id": "O1",
            "text": criterion,
            "source": "criterion",
        },
        "obligation_checks": obligations,
        "obligation_logic": logic,
        "obligation_policy": (
            "Check each source O reference separately after passing the gates. "
            "O1 retains the whole criterion including its exceptions and alternative methods. "
            "Do not turn illustrative examples or other products' obligations into mandatory elements. "
            "A compound source paragraph is not a certified atomic checklist; do not claim "
            "all elements are verified when applicability or evidence for any required element is unknown."
        ),
        "obligation_structure": (
            "SOURCE_EXPLICIT_ALTERNATIVES" if explicit_alternatives else
            "SOURCE_PLUS_EXPLICIT_REQUIREMENTS" if len(obligations) > 1 else "SOURCE_TEXT_ONLY"
        ),
        "unknown_policy": "UNDETERMINED",
    }
    if explicit_alternatives:
        contract["obligation_policy"] = (
            "Each branch preserves one source-marked allowed method including its conditions. "
            "Its O checks retain the whole method and any separately extracted explicit requirements. "
            "Check all O references separately. ANY requires one complete method, not parts "
            "borrowed across methods. Example wording/numbers are not exact-match obligations. "
            "Unknown method-specific scope or exceptions make that O UNDETERMINED."
        )
    return contract


def compile_canonical_condition_contract(rule: dict[str, Any]) -> dict[str, Any]:
    """Project a reviewed canonical plan without reparsing its prose.

    The canonical compiler already separated conditions, atomic obligations,
    owners, evidence requirements and joins. Re-running the legacy prose
    compiler would flatten those decisions and silently lose conditions.
    """
    plan = rule.get("canonical_execution_plan")
    if not isinstance(plan, dict):
        raise ValueError("canonical execution plan is required")
    facts = [
        {
            "condition_id": value["fact_id"],
            "text": value["name"],
            "source": "canonical_execution_plan",
            "condition_role": "FACT",
            "owner": value["owner"],
            "input_type": value["type"],
            "unknown_policy": value.get("unknown_policy") or "UNDETERMINED",
            **({"absence_policy": value["absence_policy"]}
               if value.get("absence_policy") else {}),
        }
        for value in plan.get("applicability_inputs") or []
    ]
    fact_ids = [value["condition_id"] for value in facts]
    decision_fact_ids = [value["fact_id"] for value in plan.get("applicability_inputs") or []
                         if value.get("purpose") == "DECISION_BRANCH"]
    applicability_logic = plan.get("applicability_logic")
    validate_applicability_expression(applicability_logic, [key for key in fact_ids if key not in decision_fact_ids])
    obligations = [
        {
            "obligation_id": value["obligation_ref"],
            "text": value["text"],
            "source": "canonical_execution_plan",
            "owners": value["owners"],
            "evidence": value["evidence_contract"],
            "interpretation_hints": value.get("interpretation_hints") or [],
            "retrieval_queries": value.get("retrieval_queries") or [value["text"]],
            **({"deterministic_adapter": value["deterministic_adapter"]}
               if value.get("deterministic_adapter") else {}),
            **({'required_terms': value['required_terms']} if value.get('required_terms') else {}),
        }
        for value in plan.get("obligations") or []
    ]
    obligation_ids = [value["obligation_id"] for value in obligations]
    obligation_logic = plan.get("obligation_logic")
    validate_expression(obligation_logic, obligation_ids, decision_fact_ids if plan.get("review_program") else None)
    source_fields = {
        "plan_ref": plan["plan_ref"],
        "source_hash": plan["source_hash"],
        "applicability_inputs": facts,
        "applicability_logic": applicability_logic,
        "obligations": obligations,
        "obligation_logic": obligation_logic,
        "source_criteria": plan.get("source_criteria") or {},
        "review_program": plan.get("review_program") or {},
        "decision_fact_ids": decision_fact_ids,
    }
    source_bytes = json.dumps(
        source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    is_template = rule.get("source_sheet") == "HWPX_TEMPLATE"
    return {
        "schema_version": VERSION,
        "canonical_plan_ref": plan["plan_ref"],
        "canonical_source_hash": plan["source_hash"],
        "review_program": plan.get("review_program") or {},
        "decision_fact_ids": decision_fact_ids,
        "source_criteria": plan.get("source_criteria") or {},
        "source_criteria_policy": plan.get("source_criteria_policy") or "",
        "scope_ref": "SCOPE",
        "scope_text": str(rule.get("question") or rule.get("title") or plan["plan_ref"]),
        "scope_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "scope_policy": "runtime-selected canonical product/template scope",
        "scope_owner": "RULE",
        "scope_metadata_fields": ["template_id" if is_template else "product_group"],
        "product_groups": list(rule.get("product_groups") or []),
        "product_subtype": rule.get("product_subtype"),
        "applicability_mode": "CANONICAL_LOGIC",
        "applicability_conditions": facts,
        "applicability_logic": applicability_logic,
        "review_conditions": [],
        "rule_relations": list(rule.get("rule_relations") or []),
        "obligation_checks": obligations,
        "obligation_logic": obligation_logic,
        "obligation_policy": (
            "Observe every atomic obligation independently. The runtime computes the "
            "authoritative ALL/ANY join; examples and neighboring rules are not evidence."
        ),
        "obligation_structure": "CANONICAL_ATOMIC",
        "unknown_policy": "UNDETERMINED",
    }


def attach_condition_contracts(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for rule in rules:
        rule["condition_contract"] = (
            compile_canonical_condition_contract(rule)
            if rule.get("canonical_execution_plan")
            else compile_condition_contract(rule)
        )
    return rules


def audit_compiled_rules(rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose remaining source-text checks instead of claiming full atomization."""
    rows = []
    seen = set()
    for rule in rules:
        item_id = rule.get("item_id")
        if not item_id or item_id in seen:
            raise ValueError("compiled audit requires unique item IDs")
        seen.add(item_id)
        contract = rule["condition_contract"]
        obligations = contract["obligation_checks"]
        validate_expression(contract["obligation_logic"], [o["obligation_id"] for o in obligations],
                            contract.get("decision_fact_ids", []) if contract.get("review_program") else None)
        rows.append({
            "item_id": item_id,
            "source_sheet": rule.get("source_sheet"),
            "product_groups": rule.get("product_groups") or [],
            "obligation_structure": contract["obligation_structure"],
            "obligation_count": len(obligations),
            "obligation_logic": contract["obligation_logic"],
            "scope_source_sha256": contract["scope_source_sha256"],
        })
    return {
        "schema_version": "compiled-obligation-audit-v1",
        "rule_count": len(rows),
        "structure_counts": {
            structure: sum(row["obligation_structure"] == structure for row in rows)
            for structure in ("SOURCE_TEXT_ONLY", "SOURCE_PLUS_EXPLICIT_REQUIREMENTS",
                              "SOURCE_EXPLICIT_ALTERNATIVES", "CANONICAL_ATOMIC")
        },
        "coverage_note": "Expression coverage is not certified semantic clause coverage; source paragraphs remain indivisible where no explicit decomposition exists.",
        "rules": rows,
    }


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
        "rule_relations": list(item.get("규칙관계") or []),
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
