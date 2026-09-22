"""Budget allocation, not semantic applicability or legal judgment."""
from __future__ import annotations


def audit_only_candidates(candidates, rules, *, reason):
    """Preserve discovery without scheduling any candidate for judgment."""
    _, audit = balanced_candidates(candidates, rules, 0)
    audit.update(
        method="discovery_audit_only_v1",
        limit=0,
        deferred_reason=reason,
    )
    return audit


def formal_judgment_candidates(
    *, template_primary, media_conditioned_v2, product_content_conditioned_v2=()
):
    """Return only tiers with a source-approved reason to execute."""
    return [
        *template_primary,
        *media_conditioned_v2,
        *product_content_conditioned_v2,
    ]


def balanced_candidates(candidates, rules, limit):
    """Reserve equal floors per present category, then redistribute by rank.

    Never synthesize candidates to fill a quota. Keep original ranking within
    the selected set; expose everything deferred by the execution budget.
    """
    if limit < 0:
        raise ValueError("candidate budget must be non-negative")
    ids = [row["item_id"] for row in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate candidate item_id")
    groups = {}
    for row in candidates:
        category = rules[row["item_id"]]["category"]
        groups.setdefault(category, []).append(row["item_id"])
    floor = limit // len(groups) if groups else 0
    chosen = {item for group in groups.values() for item in group[:floor]}
    for item in ids:
        if len(chosen) >= limit:
            break
        chosen.add(item)
    selected = [row for row in candidates if row["item_id"] in chosen]
    return selected, {
        "method": "category_floor_then_rank_v1", "limit": limit,
        "category_floor": floor,
        "available_by_category": {key: len(value) for key, value in groups.items()},
        "selected_by_category": {key: sum(item in chosen for item in value) for key, value in groups.items()},
        "selected_ids": [row["item_id"] for row in selected],
        "deferred_ids": [item for item in ids if item not in chosen],
        "deferred_reason": "execution_budget_not_inapplicability",
    }
