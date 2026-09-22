"""Build family-isolated LLM requests without mixing evidence bindings."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from rag.judgment.execution_plan_runtime import (
    ADVERTISEMENT_ROLES,
    CONTEXT_KEYS,
    EXTERNAL_ROLES,
)
from rag.judgment.family_prompts import make_batches


ALLOWED_SOURCE_ROLES = ADVERTISEMENT_ROLES | EXTERNAL_ROLES


def build_execution_requests(
    plans: list[dict[str, Any]],
    *,
    context: dict[str, str],
    evidence_by_plan: dict[str, list[dict[str, Any]]],
    selected_plan_ids: list[str] | None = None,
    max_items: int = 4,
    max_complexity: int = 12,
) -> list[dict[str, Any]]:
    """Create requests after deterministic retrieval/applicability selection.

    Evidence remains namespaced by plan.  A model therefore cannot cite a
    snippet retrieved for a neighbouring rule in the same batch.
    """
    _validate_context(context)
    indexed = _index_plans(plans)
    selected = list(indexed) if selected_plan_ids is None else selected_plan_ids
    if len(selected) != len(set(selected)) or any(plan_id not in indexed for plan_id in selected):
        raise ValueError("selected_plan_ids contain duplicate or unknown ids")
    unknown_evidence = set(evidence_by_plan) - set(indexed)
    if unknown_evidence:
        raise ValueError("evidence_by_plan contains unknown plan ids")

    normalized_evidence = {
        plan_id: _validate_evidence(rows, context, plan_id)
        for plan_id, rows in evidence_by_plan.items()
    }
    batches = make_batches([indexed[plan_id] for plan_id in selected],
                           max_items=max_items, max_complexity=max_complexity)
    requests = []
    for number, batch in enumerate(batches, 1):
        plan_inputs = []
        for projected in batch["plans"]:
            plan_id = projected["plan_ref"]
            plan_inputs.append({
                "plan": projected,
                "evidence": normalized_evidence.get(plan_id, []),
            })
        requests.append({
            "request_id": f"EXEC-{number:04}",
            "family": batch["family"],
            "system_prompt": batch["prompt"],
            "context": dict(context),
            "plan_inputs": plan_inputs,
            "response_contract": {
                "overall_verdict_forbidden": True,
                "facts_and_obligations_kept_separate": True,
                "evidence_refs_must_belong_to_same_plan": True,
                "caller_aggregates_logic": True,
            },
        })
    return requests


def request_counts(requests: list[dict[str, Any]]) -> dict[str, Any]:
    family_counts: dict[str, int] = defaultdict(int)
    plan_count = 0
    for request in requests:
        family_counts[request["family"]] += 1
        plan_count += len(request["plan_inputs"])
    return {"requests": len(requests), "plans": plan_count,
            "families": dict(sorted(family_counts.items()))}


def _validate_context(context: Any) -> None:
    if not isinstance(context, dict) or set(context) != set(CONTEXT_KEYS):
        raise ValueError("context must bind advertisement, product, revision and scope")
    if any(not isinstance(context[key], str) or not context[key].strip() for key in CONTEXT_KEYS):
        raise ValueError("context binding values must be non-empty strings")


def _index_plans(plans: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for plan in plans:
        plan_id = plan.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id or plan_id in indexed:
            raise ValueError("plans need unique non-empty plan_id values")
        indexed[plan_id] = plan
    return indexed


def _validate_evidence(rows: Any, context: dict[str, str], plan_id: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("each evidence_by_plan value must be a list")
    output = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("evidence entries must be objects")
        evidence_id = row.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in seen:
            raise ValueError("evidence ids must be unique within a plan")
        if row.get("context") != context:
            raise ValueError("evidence context differs from request context")
        if row.get("source_role") not in ALLOWED_SOURCE_ROLES:
            raise ValueError("evidence source_role cannot be a rule, example or answer")
        if row.get("plan_ref") != plan_id:
            raise ValueError("evidence must be explicitly bound to its plan")
        seen.add(evidence_id)
        output.append(dict(row))
    return output
