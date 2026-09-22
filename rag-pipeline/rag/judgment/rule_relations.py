# -*- coding: utf-8 -*-
"""Resolve explicitly authored relationships between regulation-list items."""
from __future__ import annotations

import copy
from typing import Any


def _dependency_order(
    roots: list[str], rules: dict[str, dict[str, Any]], known: set[str],
) -> list[str]:
    """Resolve declared dependencies in a stable order and reject cycles."""
    states: dict[str, int] = {}
    ordered: list[str] = []

    def visit(item_id: str) -> None:
        if item_id not in known:
            raise ValueError(f"rule relation references unknown target: {item_id}")
        if states.get(item_id) == 1:
            raise ValueError(f"cyclic rule relation: {item_id}")
        if states.get(item_id) == 2:
            return
        states[item_id] = 1
        for relation in (rules.get(item_id) or {}).get("rule_relations") or []:
            for target in relation.get("target_item_ids") or []:
                visit(target)
        states[item_id] = 2
        ordered.append(item_id)

    for root in roots:
        visit(root)
    return ordered


def expand_relation_dependencies(
    item_ids: list[str],
    rules: dict[str, dict[str, Any]],
) -> list[str]:
    """Include explicit relation targets so their verdicts are available."""
    _dependency_order(item_ids, rules, set(rules))
    expanded = list(dict.fromkeys(item_ids))
    index = 0
    while index < len(expanded):
        item_id = expanded[index]
        index += 1
        for relation in (rules.get(item_id) or {}).get("rule_relations") or []:
            for target in relation.get("target_item_ids") or []:
                if target in rules and target not in expanded:
                    expanded.append(target)
    return expanded


def apply_satisfaction_relations(
    results: dict[str, dict[str, Any]],
    rules: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Project a stronger satisfied item into a related general item.

    Relationships must come from the active regulation source. Titles,
    keywords and advertisement IDs never create an implicit relationship.
    """
    resolved = {item_id: copy.deepcopy(value) for item_id, value in results.items()}
    order = _dependency_order([key for key in rules if key in results], rules, set(rules) | set(results))
    for item_id in order:
        rule = rules.get(item_id) or {}
        if item_id not in resolved:
            continue
        if resolved[item_id].get("applicability") != "APPLICABLE":
            continue
        # Existing SATISFIED_IF authoring has no per-obligation coverage map.
        # It cannot replace several independently enumerated checks with O1.
        if len((rule.get("condition_contract") or {}).get("obligation_checks") or []) > 1:
            continue
        for relation in rule.get("rule_relations") or []:
            if relation.get("relation_type") != "SATISFIED_IF":
                continue
            target_ids = list(relation.get("target_item_ids") or [])
            target_results = [resolved.get(target) for target in target_ids]
            satisfied = [
                result for result in target_results
                if isinstance(result, dict)
                and result.get("applicability") == "APPLICABLE"
                and result.get("verdict") == "COMPLIANT"
            ]
            relation_met = (
                bool(target_ids)
                and (len(satisfied) == len(target_ids)
                     if relation.get("join", "ANY") == "ALL" else bool(satisfied))
            )
            if not relation_met:
                continue
            evidence_ids = list(dict.fromkeys(
                evidence_id for result in satisfied
                for evidence_id in result.get("evidence_ids") or []
            ))
            line_refs = list(dict.fromkeys(
                line_ref for result in satisfied
                for line_ref in result.get("evidence_line_refs") or []
            ))
            checks = [
                check for result in satisfied
                for check in result.get("requirement_checks") or []
                if isinstance(check, dict) and check.get("status") == "SATISFIED"
            ]
            source_reason = next((str(check.get("reason") or "") for check in checks
                                  if str(check.get("reason") or "").strip()), "")
            description = str(relation.get("description") or "").strip()
            resolved[item_id] = {
                **resolved[item_id],
                "verdict": "COMPLIANT",
                "evidence_ids": evidence_ids,
                "evidence_line_refs": line_refs,
                "requirement_checks": [{
                    "obligation_ref": "O1",
                    "requirement": description or "연결된 세부 규칙의 충족 결과 준용",
                    "status": "SATISFIED",
                    "finding_basis": "OBSERVED",
                    "evidence_ids": evidence_ids,
                    "evidence_line_refs": line_refs,
                    "reason": source_reason,
                }],
                "reason": description or "연결된 세부 규칙의 충족 결과를 준용했습니다.",
                "confidence": "HIGH",
                "needs_researcher_review": False,
                "relation_resolution": {
                    "relation_type": "SATISFIED_IF",
                    "target_item_ids": target_ids,
                    "satisfied_target_item_ids": [
                        target for target in target_ids
                        if isinstance(resolved.get(target), dict)
                        and resolved[target].get("applicability") == "APPLICABLE"
                        and resolved[target].get("verdict") == "COMPLIANT"
                    ],
                    "source": relation.get("source") or "REGULATION_V2",
                },
            }
    return resolved
