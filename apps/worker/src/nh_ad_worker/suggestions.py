"""Deterministic, evidence-bound fallback suggestions for review findings."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from collections.abc import Callable
from typing import Literal

from nh_ad_worker.results import ReviewResultBundle, ReviewResultItem


SuggestionType = Literal["ALTERNATIVE", "ADDITIONAL_NOTICE", "SOFTENING"]
SuggestionRefiner = Callable[[ReviewResultItem, "SuggestionProposal"], str | None]


@dataclass(frozen=True)
class SuggestionProposal:
    """A review-item suggestion before it is persisted by the job repository."""

    suggestion_id: str
    review_id: str
    review_item_id: str
    original_text: str
    suggested_text: str
    suggestion_reason: str
    suggestion_type: SuggestionType
    evidence_ids: tuple[str, ...]


def rule_suggestions(
    results: ReviewResultBundle,
    *,
    refine: SuggestionRefiner | None = None,
) -> tuple[SuggestionProposal, ...]:
    """Create safe, repeatable recommendations only for actionable Rule findings."""

    proposals: list[SuggestionProposal] = []
    for item in results.items:
        proposal = _proposal(item)
        if proposal is None:
            continue
        if refine is not None:
            try:
                refined_text = refine(item, proposal)
            except Exception:
                refined_text = None
            if isinstance(refined_text, str) and refined_text.strip():
                proposal = replace(
                    proposal,
                    suggested_text=refined_text.strip(),
                    suggestion_reason=(
                        f"{proposal.suggestion_reason} "
                        "연결된 근거 범위에서 AI가 문장을 보강했습니다."
                    ),
                )
        proposals.append(proposal)
    return tuple(proposals)


def _proposal(item: ReviewResultItem) -> SuggestionProposal | None:
    if not item.evidences:
        return None
    codes = set(item.risk_reason_codes)
    if "MISLEADING_ABSOLUTE_EXPRESSION" in codes:
        suggested_text = (
            "적용 조건을 충족하는 경우 혜택을 제공받을 수 있습니다. "
            "적용 기준과 범위는 상품설명서를 확인해 주세요."
        )
        reason = "확정적·최상급 표현을 조건부 표현으로 완화하고 적용 기준을 안내합니다."
        suggestion_type: SuggestionType = "SOFTENING"
    elif "INTEREST_RATE_CONDITION_MISSING" in codes:
        suggested_text = (
            "금리와 혜택은 적용 기간 및 우대조건에 따라 달라질 수 있습니다. "
            "세부 조건은 상품설명서를 확인해 주세요."
        )
        reason = "금리의 적용 기간·우대조건·세부 기준 고지를 보완합니다."
        suggestion_type = "ADDITIONAL_NOTICE"
    else:
        return None
    digest = (
        hashlib.sha256(f"{item.review_id}:{item.review_item_id}:{suggestion_type}".encode())
        .hexdigest()[:24]
        .upper()
    )
    return SuggestionProposal(
        suggestion_id=f"SUG-{digest}",
        review_id=item.review_id,
        review_item_id=item.review_item_id,
        original_text=item.target_text,
        suggested_text=suggested_text,
        suggestion_reason=reason,
        suggestion_type=suggestion_type,
        evidence_ids=tuple(evidence.candidate.evidence_id for evidence in item.evidences),
    )
