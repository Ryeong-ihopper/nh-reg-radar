"""Validate and combine observations for canonical execution plans."""
from __future__ import annotations

from typing import Any


TRUTH = {"TRUE": True, "FALSE": False, "UNKNOWN": None}
OBLIGATION = {"SATISFIED": True, "MISSING": False, "VIOLATED": False,
              "UNDETERMINED": None}
CONTEXT_KEYS = ("advertisement_id", "product_id", "revision_id", "scope_id")
ADVERTISEMENT_ROLES = {"ADVERTISEMENT_TEXT", "ADVERTISEMENT_REGION", "ADVERTISEMENT_SCAN"}
EXTERNAL_ROLES = {"PRODUCT_DOCUMENT", "EXTERNAL_REFERENCE", "CONFIRMED_EXTERNAL_FACT"}


def evaluate_execution_plan(plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    context = _validated_context(result.get("context"))
    evidence = _validated_evidence(result.get("evidence"), context)
    expected_facts = [row["fact_id"] for row in plan["applicability_inputs"]]
    facts = result.get("applicability")
    if not isinstance(facts, list) or [row.get("fact_ref") for row in facts] != expected_facts:
        raise ValueError("applicability results missing, duplicated, unknown or out of order")
    fact_values = {}
    for expected, row in zip(plan["applicability_inputs"], facts, strict=True):
        if row.get("status") not in TRUTH:
            raise ValueError("invalid applicability status")
        status = row["status"]
        refs = row.get("evidence_refs") or []
        referenced = _resolve_evidence(refs, evidence)
        owner = expected["owner"]
        if owner == "RULE" and status != "UNKNOWN" and row.get("basis") != "CONFIRMED_METADATA":
            raise ValueError("rule-owned applicability needs confirmed metadata")
        if "LLM" in owner and status == "TRUE":
            if not any(item["source_role"] in ADVERTISEMENT_ROLES for item in referenced):
                raise ValueError("observed applicability needs advertisement evidence")
        if "LLM" in owner and status == "FALSE":
            if result.get("complete_scan") is not True:
                raise ValueError("negative semantic applicability needs complete scan")
        if "EXTERNAL" in owner and status != "UNKNOWN":
            if not any(item["source_role"] in EXTERNAL_ROLES for item in referenced):
                raise ValueError("external applicability needs external evidence")
        fact_values[row["fact_ref"]] = TRUTH[row["status"]]
    applicable = _walk(plan["applicability_logic"], fact_values)
    if applicable is False:
        return _out(plan, "NOT_APPLICABLE", [], [])
    if applicable is None:
        return _out(plan, "UNDETERMINED", [], [])

    expected_atoms = [row["obligation_id"] for row in plan["obligations"]]
    checks = result.get("obligations")
    if not isinstance(checks, list) or [row.get("obligation_ref") for row in checks] != expected_atoms:
        raise ValueError("obligation results missing, duplicated, unknown or out of order")
    values = {}
    human_queue = []
    for atom, check in zip(plan["obligations"], checks, strict=True):
        status = check.get("status")
        if status not in OBLIGATION:
            raise ValueError("invalid obligation status")
        evidence_refs = check.get("evidence_refs")
        if not isinstance(evidence_refs, list):
            raise ValueError("evidence_refs must be a list")
        referenced = _resolve_evidence(evidence_refs, evidence)
        if status in {"SATISFIED", "VIOLATED"} and atom["evidence"]["advertisement_direct_quote_required"]:
            if not any(row["source_role"] in ADVERTISEMENT_ROLES for row in referenced):
                raise ValueError("observed semantic result needs direct evidence")
        if status == "MISSING" and atom["evidence"]["absence_requires_complete_scan"]:
            if result.get("complete_scan") is not True:
                status = "UNDETERMINED"
        if atom["owners"]["external_input"]:
            external_verified = check.get("external_input_verified") is True
            external_evidence = any(row["source_role"] in EXTERNAL_ROLES for row in referenced)
            if not external_verified or not external_evidence:
                status = "UNDETERMINED"
        if atom["owners"]["human"] and status == "UNDETERMINED":
            human_queue.append({"obligation_ref": atom["obligation_id"],
                                "question": atom["text"], "evidence_refs": evidence_refs})
        values[atom["obligation_id"]] = OBLIGATION[status]
    combined = _walk(plan["obligation_logic"], values)
    verdict = "COMPLIANT" if combined is True else "VIOLATION" if combined is False else "UNDETERMINED"
    return _out(plan, verdict, checks, human_queue)


def _validated_context(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(CONTEXT_KEYS):
        raise ValueError("context must bind advertisement, product, revision and scope")
    if any(not isinstance(value[key], str) or not value[key].strip() for key in CONTEXT_KEYS):
        raise ValueError("context binding values must be non-empty strings")
    return {key: value[key] for key in CONTEXT_KEYS}


def _validated_evidence(value: Any, context: dict[str, str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("evidence must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("evidence entries must be objects")
        evidence_id = row.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in indexed:
            raise ValueError("evidence ids must be unique non-empty strings")
        if row.get("context") != context:
            raise ValueError("evidence context differs from request context")
        if row.get("source_role") not in ADVERTISEMENT_ROLES | EXTERNAL_ROLES:
            raise ValueError("unknown evidence source role")
        indexed[evidence_id] = row
    return indexed


def _resolve_evidence(refs: list[Any], evidence: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if len(refs) != len(set(refs)) or any(ref not in evidence for ref in refs):
        raise ValueError("evidence_refs contain duplicate or unknown ids")
    return [evidence[ref] for ref in refs]


def _walk(node: dict[str, Any], values: dict[str, bool | None]) -> bool | None:
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError("invalid expression")
    op, arg = next(iter(node.items()))
    if op in {"fact", "ref"}:
        if arg not in values:
            raise ValueError(f"unknown expression reference: {arg}")
        return values[arg]
    if op == "not":
        value = _walk(arg, values)
        return None if value is None else not value
    if op not in {"all", "any"} or not isinstance(arg, list) or not arg:
        raise ValueError("invalid expression operator or children")
    children = [_walk(child, values) for child in arg]
    decisive = op == "any"
    if any(value is decisive for value in children):
        return decisive
    if None in children:
        return None
    return not decisive


def _out(plan: dict[str, Any], verdict: str, checks: list, human_queue: list) -> dict[str, Any]:
    return {"plan_id": plan["plan_id"], "verdict": verdict,
            "obligation_results": checks, "human_review_queue": human_queue,
            "source_sha256": plan["source_sha256"], "operationally_connected": True}
