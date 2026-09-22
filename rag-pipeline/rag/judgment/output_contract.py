"""Wire shape constraints, not semantic decisions or source-derived obligations."""
from __future__ import annotations

import os
from typing import Any


def response_mode() -> str:
    mode = os.environ.get("NH_JUDGE_RESPONSE_FORMAT", "json_schema")
    if mode not in {"json_schema", "json_object"}:
        raise ValueError("NH_JUDGE_RESPONSE_FORMAT must be json_schema or json_object")
    return mode


def response_format(compact: dict[str, Any]) -> dict[str, Any]:
    """Constrain shape/known aliases; existing validator still checks all semantics.

    Unsupported endpoints must be configured explicitly with json_object. Never
    silently downgrade on a server error or synthesize a successful judgment.
    Empty requirement arrays remain legal for failed/unknown applicability gates.
    """
    if response_mode() == "json_object":
        return {"type": "json_object"}

    def enum(values: list[str]) -> dict[str, Any]:
        return {"type": "string", "enum": list(dict.fromkeys(values))}

    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    def refs(values: list[str]) -> dict[str, Any]:
        return {"type": "array", "items": enum(values) if values else {"type": "string"},
                **({"maxItems": 0} if not values else {})}

    rules = compact["rules"]
    aliases = list(dict.fromkeys(
        alias for scope in compact["evidence_scope"].values()
        for key in ("evidence_refs", "line_refs") for alias in scope[key]))
    evidence = refs(aliases)
    metadata = {"type": "array", "items": {"type": "string"}}
    text = {"type": "string", "minLength": 1}

    def gate_checks(field: str, statuses: list[str]) -> dict[str, Any]:
        allowed = list(dict.fromkeys(ref for rule in rules
            for ref in (rule.get("output_check_refs") or {}).get(field, [])))
        lengths = [len((rule.get("output_check_refs") or {}).get(field, [])) for rule in rules]
        # Every source gate needs a check even when scope is unmatched. Keep
        # mixed batches permissive enough for each rule; the validator checks
        # the exact per-rule IDs and order after decoding.
        return {"type": "array", "items": obj({
            "condition_ref": enum(allowed) if allowed else {"type": "string"},
            "status": enum(statuses), "evidence_refs": evidence, "metadata_fields": metadata}),
            "minItems": min(lengths, default=0), "maxItems": max(lengths, default=0)}

    obligation_refs = list(dict.fromkeys(ref for rule in rules
        for ref in (rule.get("output_check_refs") or {}).get("requirement_checks", [])))
    requirement = obj({
        **({"obligation_ref": enum(obligation_refs)} if obligation_refs else {}),
        "requirement": text,
        "status": enum(["SATISFIED", "MISSING", "VIOLATED", "UNDETERMINED"]),
        "finding_basis": enum(["OBSERVED", "ABSENCE", "CONFIRMED_METADATA", "UNKNOWN"]),
        "evidence_refs": evidence, "reason": text})
    if obligation_refs and not all("requirement_checks" in (rule.get("output_check_refs") or {}) for rule in rules):
        # A mixed legacy/v2 batch must still allow a legacy check without O IDs.
        requirement["required"].remove("obligation_ref")
    result = obj({
        "rule_ref": enum([rule["rule_ref"] for rule in rules]),
        "scope_check": obj({"scope_ref": enum(["SCOPE"]),
            "status": enum(["MATCHED", "NOT_MATCHED", "UNDETERMINED"]),
            "evidence_refs": evidence, "metadata_fields": metadata}),
        "condition_checks": gate_checks("condition_checks", ["SATISFIED", "NOT_SATISFIED", "UNDETERMINED"]),
        "review_condition_checks": gate_checks("review_condition_checks", ["TRIGGERED", "NOT_TRIGGERED", "UNDETERMINED"]),
        "verdict": enum(["COMPLIANT", "VIOLATION", "UNDETERMINED"]),
        "requirement_checks": {"type": "array", "items": requirement},
        "reason": text, "confidence": enum(["LOW", "MEDIUM", "HIGH"])})
    schema = obj({"results": {"type": "array", "items": result,
                              "minItems": len(rules), "maxItems": len(rules)}})
    return {"type": "json_schema", "json_schema": {
        "name": "advertisement_judgment_wire", "strict": True, "schema": schema}}
