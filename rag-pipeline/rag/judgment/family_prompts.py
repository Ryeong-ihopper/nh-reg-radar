"""Short, role-preserving prompts and deterministic complexity batching."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


BASE = """Return structured fact observations only. Use each obligation's allowed
advertisement evidence and confirmed metadata. Keep applicability, exceptions,
and obligations separate. UNKNOWN is required when a necessary input is absent.
Never use a rule, example, guidance, or another rule's evidence as advertisement
proof. A NON_BINDING_SOURCE_EXAMPLE may clarify meaning and retrieval vocabulary,
but it is never an exact-match requirement. A retrieval miss is not proof of absence. Give a short direct citation
for every semantic observation; do not provide hidden or extended reasoning.
The caller calculates AND/OR/NOT, numeric results, and the overall verdict."""

FAMILY = {
    "SEMANTIC_PRESENCE_OR_PROHIBITION": """For each O, decide only whether the cited
advertisement text expresses the required meaning or the prohibited meaning.
Distinguish negation, warning, possibility, condition, and definite promise.
Do not add attributes that the obligation does not require.""",
    "DETERMINISTIC_FORMAT_OR_NUMBER": """Extract the exact observed value, unit,
date, format position, and citation. Do not calculate or normalize it. If the
source structure needed to identify first position or line is unavailable,
return UNKNOWN.""",
    "HYBRID_FACT_SEMANTIC": """Return semantic role observations separately from
exact values. Identify what each value describes before the caller compares it.
Do not decide the overall rule from a keyword or one satisfied component.""",
    "EXTERNAL_COMPARISON": """Bind every observation to advertisement, product,
revision, period, unit, and source role. Never compare values with a different
binding. If the required product document or external fact is absent, return
UNKNOWN rather than guessing from the advertisement.""",
    "HYBRID_VISUAL": """Judge only text meaning from citable text. Emit a human
review request with source region references for size, color, contrast, spacing,
proximity, logo, or visual grouping; do not infer those properties from OCR text.""",
    "HUMAN_VISUAL": """Do not produce an automated compliance judgment. Return the
source regions and the exact visual question that a human must check.""",
}


def prompt_for_family(family: str) -> str:
    if family not in FAMILY:
        raise ValueError(f"unknown prompt family: {family}")
    return BASE + "\n\n" + FAMILY[family]


def project_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Project only role-tagged fields; display examples are never included."""
    return {
        "plan_ref": plan["plan_id"],
        "applicability_inputs": plan["applicability_inputs"],
        "applicability_logic": plan["applicability_logic"],
        "obligations": [{
            "obligation_ref": atom["obligation_id"],
            "text": atom["text"],
            "owners": atom["owners"],
            "evidence_contract": atom["evidence"],
            "interpretation_hints": atom.get("interpretation_hints") or [],
            "retrieval_queries": atom.get("retrieval_queries") or [atom["text"]],
            **({"deterministic_adapter": atom["deterministic_adapter"]}
               if atom.get("deterministic_adapter") else {}),
        } for atom in plan["obligations"]],
        "obligation_logic": plan["obligation_logic"],
        "source_hash": plan["source_sha256"],
    }


def make_batches(plans: list[dict[str, Any]], *, max_items: int = 4,
                 max_complexity: int = 12) -> list[dict[str, Any]]:
    """Keep families separate and cap both count and actual plan complexity."""
    if max_items < 1 or max_complexity < 1:
        raise ValueError("batch limits must be positive")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for plan in plans:
        groups[plan["prompt_family"]].append(plan)
    output = []
    for family in sorted(groups):
        current: list[dict[str, Any]] = []
        weight = 0
        for plan in groups[family]:
            plan_weight = int(plan["complexity"])
            if plan_weight > max_complexity:
                if current:
                    output.append(_batch(family, current, weight))
                    current, weight = [], 0
                output.append(_batch(family, [plan], plan_weight))
                continue
            if current and (len(current) >= max_items or weight + plan_weight > max_complexity):
                output.append(_batch(family, current, weight))
                current, weight = [], 0
            current.append(plan)
            weight += plan_weight
        if current:
            output.append(_batch(family, current, weight))
    return output


def _batch(family: str, plans: list[dict[str, Any]], weight: int) -> dict[str, Any]:
    return {
        "family": family,
        "prompt": prompt_for_family(family),
        "complexity": weight,
        "plans": [project_plan(plan) for plan in plans],
        "operationally_connected": True,
    }
