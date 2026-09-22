"""Offline, evidence-bound predicate evaluation; no extraction or legal inference.

Plans are authored from source clauses. Inputs are separately verified observations,
not model explanations. This module does not certify their semantic correctness.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def validate_plan(plan: dict) -> None:
    specs = plan["facts"]
    seen: set[str] = set()
    count = 0

    def visit(node: dict, depth: int = 0) -> None:
        nonlocal count
        count += 1
        if depth > 24 or count > 512 or not isinstance(node, dict) or len(node) != 1:
            raise ValueError("invalid or oversized expression")
        op, arg = next(iter(node.items()))
        if op == "fact":
            if arg not in specs:
                raise ValueError(f"undefined fact: {arg}")
            seen.add(arg)
        elif op == "unknown":
            if not isinstance(arg, str) or not arg:
                raise ValueError("unresolved clause needs a reason")
        elif op in {"all", "any"}:
            if not isinstance(arg, list) or not arg:
                raise ValueError("empty conjunction/disjunction")
            for child in arg:
                visit(child, depth + 1)
        elif op == "not":
            visit(arg, depth + 1)
        elif op == "if":
            if not isinstance(arg, list) or len(arg) != 3:
                raise ValueError("if needs condition, then and else")
            for child in arg:
                visit(child, depth + 1)
        elif op == "le_sum":
            if not isinstance(arg, list) or len(arg) != 2:
                raise ValueError("le_sum needs maximum and component facts")
            for key in arg:
                visit({"fact": key}, depth + 1)
            left, right = (specs[key] for key in arg)
            if (left["type"], right["type"]) != ("decimal", "decimal_list"):
                raise ValueError("invalid comparison types")
            if not left.get("unit") or left.get("unit") != right.get("unit"):
                raise ValueError("comparison units differ")
        else:
            raise ValueError(f"unknown operator: {op}")

    visit(plan["scope"])
    visit(plan["expression"])
    if seen != set(specs):
        raise ValueError("unused fact declarations")
    for spec in specs.values():
        if spec["type"] not in {"bool", "decimal", "decimal_list"}:
            raise ValueError("invalid fact type")
        if not spec.get("sources") or not spec.get("owner"):
            raise ValueError("fact provenance contract missing")
    if plan.get("on_false", "VIOLATION") not in {"VIOLATION", "REVIEW_REQUIRED"}:
        raise ValueError("invalid failure route")


def evaluate_plan(plan: dict, payload: dict) -> dict:
    """Calculate a local result without touching stored reviews or calling an LLM.

All references must belong to the same advertisement/product/revision/scope.
ABSENT observations additionally require a verified complete scan. A search miss
is not such a scan. Source type and reviewer ownership are checked per fact.
"""
    validate_plan(plan)
    context = payload["context"]
    for key in ("advertisement", "product", "revision", "scope"):
        if not isinstance(context.get(key), str) or not context[key]:
            raise ValueError(f"context needs {key}")
    audit: dict[str, dict] = {}
    trace: list[dict] = []

    def read(key: str) -> Any:
        if key in audit:
            return audit[key]["value"]
        spec = plan["facts"][key]
        item = payload.get("facts", {}).get(key)
        reason = "MISSING_INPUT"
        value = None
        if isinstance(item, dict):
            refs = item.get("evidence_refs", [])
            records = [payload.get("evidence", {}).get(ref) for ref in refs]
            valid = (
                item.get("verified") is True
                and item.get("owner") == spec["owner"]
                and bool(records)
                and all(isinstance(r, dict) and r.get("verified") is True
                        and r.get("context") == context
                        and r.get("source_type") in spec["sources"]
                        and bool(r.get("locator")) for r in records)
            )
            reason = "INVALID_PROVENANCE"
            if valid:
                value = item.get("value")
                reason = "VALIDATED"
                if value is False and spec.get("false_requires_scan") and item.get("mode") != "ABSENT":
                    value, reason = None, "ABSENCE_WITHOUT_COMPLETE_SCAN"
                if item.get("mode") == "ABSENT":
                    scan = payload.get("scans", {}).get(item.get("scan_ref"), {})
                    if not (spec["type"] == "bool" and value is False
                            and scan.get("verified") is True
                            and scan.get("complete") is True
                            and scan.get("context") == context
                            and set(refs) <= set(scan.get("evidence_refs", []))):
                        value, reason = None, "ABSENCE_WITHOUT_COMPLETE_SCAN"
                elif item.get("mode") != "OBSERVED":
                    value, reason = None, "UNKNOWN_OBSERVATION_MODE"
                if value is not None:
                    try:
                        if spec["type"] == "bool":
                            if type(value) is not bool:
                                raise ValueError("not boolean")
                        else:
                            if item.get("unit") != spec.get("unit"):
                                raise ValueError("unit mismatch")
                            if spec["type"] == "decimal_list":
                                if not isinstance(value, list) or not value or item.get("complete") is not True:
                                    raise ValueError("incomplete component list")
                                component_refs = item.get("component_refs", [])
                                if (len(component_refs) != len(value)
                                        or len(set(component_refs)) != len(component_refs)
                                        or not set(component_refs) <= set(refs)):
                                    raise ValueError("components need distinct verified evidence references")
                                value = [_number(v) for v in value]
                            else:
                                value = _number(value)
                    except (ValueError, InvalidOperation):
                        value, reason = None, "INVALID_VALUE_OR_UNIT"
        audit[key] = {"value": value, "reason": reason,
                      "evidence_refs": item.get("evidence_refs", []) if isinstance(item, dict) else []}
        return value

    def truth(value: Any) -> bool | None:
        if value is not None and type(value) is not bool:
            raise ValueError("numeric fact used as boolean")
        return value

    def walk(node: dict) -> bool | None:
        op, arg = next(iter(node.items()))
        if op == "fact":
            result = truth(read(arg))
        elif op == "unknown":
            result = None
        elif op == "not":
            child = walk(arg)
            result = None if child is None else not child
        elif op in {"all", "any"}:
            values = [walk(child) for child in arg]
            decisive = op == "any"
            result = decisive if any(v is decisive for v in values) else (
                None if None in values else not decisive)
        elif op == "if":
            condition = walk(arg[0])
            # Unknown applicability never selects or waives an obligation.
            result = None if condition is None else walk(arg[1] if condition else arg[2])
        elif op == "le_sum":
            maximum, components = (read(key) for key in arg)
            result = None if maximum is None or components is None else maximum <= sum(components)
        else:
            raise ValueError(op)
        trace.append({"operator": op, "argument": arg, "result": result})
        return result

    scope = walk(plan["scope"])
    if scope is not True:
        verdict = "NOT_APPLICABLE" if scope is False else "UNDETERMINED"
    else:
        result = walk(plan["expression"])
        verdict = "COMPLIANT" if result is True else (
            plan.get("on_false", "VIOLATION") if result is False else "UNDETERMINED")
    # Convert Decimal audit values to JSON-safe strings without binary rounding.
    def serial(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, list):
            return [serial(v) for v in value]
        if isinstance(value, dict):
            return {k: serial(v) for k, v in value.items()}
        return value
    return {"plan_id": plan["plan_id"], "verdict": verdict, "scope": scope,
            "facts": serial(audit), "trace": trace,
            "human_review": [{"fact": key, "description": plan["facts"][key].get("description", key),
                              "evidence_refs": item["evidence_refs"]}
                             for key, item in audit.items()
                             if item["value"] is None and plan["facts"][key]["owner"] == "HUMAN"],
            "source_review": list(dict.fromkeys(
                item["argument"] for item in trace if item["operator"] == "unknown")),
            "source_refs": plan.get("source_refs", []), "operational": False}


def _number(value: Any) -> Decimal:
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError("decimal inputs must be exact strings or integers")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("invalid nonnegative quantity")
    return result
