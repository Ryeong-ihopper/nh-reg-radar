"""Evaluate source-authored obligation joins, never infer joins from prose.

Evidence and applicability validation remain the caller's responsibility.
A failed alternative is not an independent mandatory obligation.
"""

from __future__ import annotations

from typing import Any


STATUSES = {"SATISFIED", "MISSING", "VIOLATED", "UNDETERMINED", "NOT_APPLICABLE"}
FACT_STATUSES = {"SATISFIED", "NOT_SATISFIED", "UNDETERMINED"}


def validate_expression(expression: Any, obligation_ids: list[str], fact_ids: list[str] | None = None) -> None:
    if (not obligation_ids and fact_ids is None) or len(set(obligation_ids)) != len(obligation_ids):
        raise ValueError("obligation logic needs unique non-empty obligation IDs")
    seen: set[str] = set()
    nodes = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > 24 or nodes > 512:
            raise ValueError("obligation logic exceeds complexity limit")
        if not isinstance(node, dict) or len(node) != 1:
            raise ValueError("obligation logic needs exactly one operator per node")
        operator, value = next(iter(node.items()))
        if operator == "ref":
            if not isinstance(value, str) or value not in obligation_ids:
                raise ValueError("obligation logic references an unknown obligation")
            seen.add(value)
        elif operator == "fact" and fact_ids is not None and value in fact_ids:
            pass
        elif operator == "unknown" and fact_ids is not None and isinstance(value, str) and value:
            pass
        elif operator == "not" and fact_ids is not None:
            visit(value, depth + 1)
        elif operator == "if" and fact_ids is not None and isinstance(value, list) and len(value) == 3:
            for child in value:
                visit(child, depth + 1)
        elif operator in {"all", "any"} and isinstance(value, list) and value:
            for child in value:
                visit(child, depth + 1)
        else:
            raise ValueError("obligation logic requires ref or non-empty all/any")

    visit(expression, 0)
    if seen != set(obligation_ids):
        raise ValueError("obligation logic omits source obligations")


def aggregate_obligations(contract: dict[str, Any], checks: Any, condition_checks: Any = None) -> str:
    """Return the verdict forced by a complete, ordered source checklist.

    An unknown leaf stays unknown. ALL fails on a proven failed conjunct;
    ANY passes on a proven successful branch, even if another is unresolved.
    NOT_APPLICABLE at an obligation is not permission to waive that obligation.
    """
    expression = contract["obligation_logic"]
    expected = [value["obligation_id"] for value in contract["obligation_checks"]]
    program = contract.get("review_program") or {}
    decision_facts = contract.get("decision_fact_ids") or []
    validate_expression(expression, expected, decision_facts if program else None)
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise ValueError("obligation checks must be objects")
    if [c.get("obligation_ref") for c in checks] != expected:
        raise ValueError("obligation checks missing, duplicated, unknown or out of order")
    states = {}
    for check in checks:
        status = check.get("status")
        if status not in STATUSES:
            raise ValueError("invalid obligation status")
        states[check["obligation_ref"]] = (
            True if status == "SATISFIED" else False if status in {"MISSING", "VIOLATED"} else None
        )

    def evaluate(node: dict[str, Any]) -> bool | None:
        if "ref" in node:
            return states[node["ref"]]
        if "fact" in node:
            values = {row.get("condition_ref"): row.get("status") for row in condition_checks or []}
            value = values.get(node["fact"])
            return True if value == "SATISFIED" else False if value == "NOT_SATISFIED" else None
        if "unknown" in node:
            return None
        if "not" in node:
            value = evaluate(node["not"])
            return None if value is None else not value
        if "if" in node:
            condition, yes, no = node["if"]
            value = evaluate(condition)
            return None if value is None else evaluate(yes if value else no)
        operator, children = next(iter(node.items()))
        values = [evaluate(child) for child in children]
        decisive = operator == "any"
        if any(value is decisive for value in values):
            return decisive
        if None in values:
            return None
        return not decisive

    result = evaluate(expression)
    verdict = "COMPLIANT" if result is True else "VIOLATION" if result is False else "UNDETERMINED"
    allowed = program.get("allowed_outcomes")
    return verdict if not allowed or verdict in allowed else "UNDETERMINED"


def validate_applicability_expression(expression: Any, fact_ids: list[str]) -> None:
    """Validate a source-authored applicability expression.

    Applicability supports NOT because an authored exception is a negated fact.
    Obligation joins intentionally remain limited to ALL/ANY.
    """
    if len(set(fact_ids)) != len(fact_ids) or any(not value for value in fact_ids):
        raise ValueError("applicability logic needs unique non-empty fact IDs")
    seen: set[str] = set()
    nodes = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > 24 or nodes > 512:
            raise ValueError("applicability logic exceeds complexity limit")
        if not isinstance(node, dict) or len(node) != 1:
            raise ValueError("applicability logic needs exactly one operator per node")
        operator, value = next(iter(node.items()))
        if operator == "fact":
            if not isinstance(value, str) or value not in fact_ids:
                raise ValueError("applicability logic references an unknown fact")
            seen.add(value)
        elif operator == "not":
            visit(value, depth + 1)
        elif operator in {"all", "any"} and isinstance(value, list) and value:
            for child in value:
                visit(child, depth + 1)
        else:
            raise ValueError("applicability logic requires fact, not, or non-empty all/any")

    visit(expression, 0)
    if seen != set(fact_ids):
        raise ValueError("applicability logic omits source facts")


def aggregate_applicability(
    contract: dict[str, Any], scope_status: str | None, checks: Any,
) -> str:
    """Calculate applicability from scope and ordered atomic fact observations."""
    if scope_status == "NOT_MATCHED":
        return "NOT_APPLICABLE"
    if scope_status != "MATCHED":
        return "UNDETERMINED"
    conditions = contract.get("applicability_conditions") or []
    expected = [value["condition_id"] for value in conditions]
    expression = contract.get("applicability_logic")
    if expression is None:
        expression = {"all": [{"fact": value} for value in expected]} if expected else {"all": [{"fact": "__SCOPE__"}]}
    if not expected:
        return "APPLICABLE"
    decision_facts = set(contract.get("decision_fact_ids") or [])
    validate_applicability_expression(expression, [key for key in expected if key not in decision_facts])
    if not isinstance(checks, list) or any(not isinstance(value, dict) for value in checks):
        raise ValueError("applicability checks must be objects")
    if [value.get("condition_ref") for value in checks] != expected:
        raise ValueError("applicability checks missing, duplicated, unknown or out of order")
    states: dict[str, bool | None] = {}
    for check in checks:
        status = check.get("status")
        if status not in FACT_STATUSES:
            raise ValueError("invalid applicability fact status")
        states[check["condition_ref"]] = (
            True if status == "SATISFIED" else False if status == "NOT_SATISFIED" else None
        )

    def evaluate(node: dict[str, Any]) -> bool | None:
        operator, value = next(iter(node.items()))
        if operator == "fact":
            return states[value]
        if operator == "not":
            child = evaluate(value)
            return None if child is None else not child
        values = [evaluate(child) for child in value]
        decisive = operator == "any"
        if any(child is decisive for child in values):
            return decisive
        if None in values:
            return None
        return not decisive

    result = evaluate(expression)
    return "APPLICABLE" if result is True else "NOT_APPLICABLE" if result is False else "UNDETERMINED"


OBLIGATION_LOGIC_PROMPT = """
When condition_contract.obligation_logic is present, it is the authoritative
join of the listed O checks: all means every child, any means at least one
complete child. Return every O check in source order, including unresolved
alternatives; do not invent O IDs or change the expression.
Evaluate scope and conditions first. An O whose own conditions or exceptions
are unresolved is UNDETERMINED, not MISSING or VIOLATED. Unsupported inputs
remain unknown. Keep each O's own source wording and exception boundaries.
The runtime independently validates the overall verdict using this expression.
For review programs, fact refers to a decision fact rather than a whole-rule
applicability condition. if selects the true/false branch only when its fact is
known; unknown leaves the branch unresolved. not negates a known fact only.
The review program's allowed_outcomes limits the final decision. REVIEW_ONLY
does not permit automatic compliance or violation and has no invented duty.
A failed alternative does not force VIOLATION when a complete allowed method
is SATISFIED. A failed mandatory conjunct does force VIOLATION even if another
independent conjunct is unknown, after applicability/exception gates pass.

Synthetic logic examples (not legal rules, evidence or exact required wording):
1. any(O1,O2): O1=SATISFIED, O2=UNDETERMINED -> COMPLIANT.
2. any(O1,O2): O1=MISSING, O2=UNDETERMINED -> UNDETERMINED.
3. all(O1,O2): O1=SATISFIED, O2=UNDETERMINED -> UNDETERMINED.
4. all(O1,O2): O1=VIOLATED, O2=UNDETERMINED -> VIOLATION.
MISSING in these examples presupposes a complete reliable scan; never infer
absence from retrieval failure. An applicability UNKNOWN never becomes false.
Provide short, direct evidence per O, not an extended chain of thought.
"""
