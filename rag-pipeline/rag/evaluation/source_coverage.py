"""Measure whether every formal prediction source is represented in evaluation."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any


def evaluation_source_coverage(
    predictions: Iterable[Mapping[str, Any]],
    scored_keys: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    """Summarize scored and unscored formal predictions by source and tier.

    ``predictions`` must already be limited to the formal review surface. Audit-only
    discoveries are intentionally outside this denominator.
    """
    scored = set(scored_keys)
    seen: set[tuple[str, str]] = set()
    by_source: Counter[tuple[str, bool]] = Counter()
    by_tier: Counter[tuple[str, bool]] = Counter()
    for row in predictions:
        key = (str(row["review_id"]), str(row["item_id"]))
        if key in seen:
            raise ValueError(f"duplicate formal prediction: {key}")
        seen.add(key)
        is_scored = key in scored
        by_source[(str(row["source_type"]), is_scored)] += 1
        by_tier[(str(row["discovery_tier"]), is_scored)] += 1
    unknown_scored = sorted(scored - seen)

    def groups(counter: Counter[tuple[str, bool]]) -> dict[str, dict[str, Any]]:
        names = sorted(name for name, _ in counter)
        return {
            name: {
                "formal_rows": counter[(name, True)] + counter[(name, False)],
                "scored_rows": counter[(name, True)],
                "unscored_rows": counter[(name, False)],
                "score_coverage": (
                    counter[(name, True)] /
                    (counter[(name, True)] + counter[(name, False)])
                ),
            }
            for name in names
        }

    scored_rows = sum(value for (name, flag), value in by_source.items() if flag)
    unscored_rows = sum(value for (name, flag), value in by_source.items() if not flag)
    return {
        "formal_rows": scored_rows + unscored_rows,
        "scored_rows": scored_rows,
        "unscored_rows": unscored_rows,
        "score_coverage": scored_rows / (scored_rows + unscored_rows)
        if scored_rows + unscored_rows else 1.0,
        "by_source": groups(by_source),
        "by_discovery_tier": groups(by_tier),
        "unknown_scored_keys": [
            {"review_id": review_id, "item_id": item_id}
            for review_id, item_id in unknown_scored
        ],
        "overall_accuracy_claim_allowed": unscored_rows == 0 and not unknown_scored,
        "gate_reason": None if unscored_rows == 0 and not unknown_scored else
        "formal execution includes rows without gold labels",
    }
