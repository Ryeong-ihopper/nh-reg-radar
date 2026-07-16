"""HTTP handlers for the frozen M4 Review API."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.reviews import Review, ReviewBundle, ReviewService


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


ReviewType = Literal[
    "REQUIRED_PHRASE",
    "INTEREST_RATE",
    "MISLEADING_EXPRESSION",
    "PRODUCT_CONSISTENCY",
    "VISIBILITY",
    "OCR_QUALITY",
]


class CreateReviewRequest(StrictModel):
    standardEffectiveDate: date | None = None
    reviewTypes: list[ReviewType] | None = Field(None, min_length=1)
    includeSuggestion: bool = True
    includeOpinionDraft: bool = False
    requestMemo: str | None = Field(None, max_length=2000)


class RerunReviewRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)
    reviewTypes: list[ReviewType] | None = Field(None, min_length=1)


def accepted(bundle: ReviewBundle) -> dict[str, object]:
    review = bundle.review
    return {
        "reviewId": review.review_id,
        "advertisementId": review.advertisement_id,
        "reviewStatus": review.status,
        "jobId": bundle.job.job_id,
        "standardEffectiveDate": review.standard_effective_date,
        "standardVersionIds": list(review.standard_version_ids),
        "requestedAt": review.requested_at,
    }


def history(review: Review) -> dict[str, object]:
    return {
        "reviewId": review.review_id,
        "reviewRound": review.review_round,
        "reviewStatus": review.status,
        "overallRiskLevel": review.overall_risk_level,
        "requestedAt": review.requested_at,
        "completedAt": review.completed_at,
    }


def progress(bundle: ReviewBundle) -> dict[str, object]:
    job = bundle.job
    return {
        "reviewId": bundle.review.review_id,
        "advertisementId": bundle.review.advertisement_id,
        "reviewStatus": bundle.review.status,
        "jobId": job.job_id,
        "jobStatus": job.status,
        "currentStep": job.current_step,
        "progressRate": job.progress_rate,
        "retryCount": job.retry_count,
        "maxRetries": job.max_retries,
        "nextRetryAt": job.next_retry_at,
        "isRetryable": job.is_retryable,
        "failedReasonCode": job.failed_reason_code,
        "failedReason": job.failed_reason,
        "timeoutAt": job.timeout_at,
        "steps": [
            {
                "stepCode": step.step_code,
                "stepName": step.step_name,
                # A completed job is authoritative for the progress projection.
                # This also makes progress responses from jobs completed before
                # the worker began persisting FILE_PREPROCESSING completion
                # internally consistent.
                "status": "COMPLETED" if job.status == "COMPLETED" else step.status,
                "timeoutAt": step.timeout_at,
                "failedReasonCode": step.failed_reason_code,
            }
            for step in bundle.steps
        ],
        "updatedAt": job.updated_at,
    }


def install_review_routes(
    router: APIRouter,
    service: ReviewService,
    actor_dependency: object,
) -> None:
    Actor = Annotated[CurrentUser, Depends(actor_dependency)]

    @router.post(
        "/advertisements/{advertisementId}/reviews",
        status_code=202,
        operation_id="requestAdvertisementReview",
    )
    async def request_review(
        payload: CreateReviewRequest,
        request: Request,
        current: Actor,
        advertisement_id: Annotated[
            str, Path(alias="advertisementId", pattern=r"^ADV-[A-Za-z0-9-]+$")
        ],
    ) -> dict[str, object]:
        return accepted(
            service.request(
                current,
                advertisement_id,
                standard_effective_date=payload.standardEffectiveDate,
                review_types=tuple(payload.reviewTypes) if payload.reviewTypes else None,
                include_suggestion=payload.includeSuggestion,
                include_opinion_draft=payload.includeOpinionDraft,
                request_memo=payload.requestMemo,
                trace_id=request.state.trace_id,
            )
        )

    @router.get(
        "/advertisements/{advertisementId}/reviews",
        operation_id="listAdvertisementReviews",
    )
    async def list_reviews(
        request: Request,
        current: Actor,
        advertisement_id: Annotated[
            str, Path(alias="advertisementId", pattern=r"^ADV-[A-Za-z0-9-]+$")
        ],
    ) -> list[dict[str, object]]:
        return [
            history(item)
            for item in service.list(current, advertisement_id, request.state.trace_id)
        ]

    @router.get("/reviews/{reviewId}/status", operation_id="getReviewStatus")
    async def get_status(
        request: Request,
        current: Actor,
        review_id: Annotated[str, Path(alias="reviewId", pattern=r"^REV-[A-Za-z0-9-]+$")],
    ) -> dict[str, object]:
        return progress(service.status(current, review_id, request.state.trace_id))

    @router.post("/reviews/{reviewId}/rerun", status_code=202, operation_id="rerunReview")
    async def rerun_review(
        payload: RerunReviewRequest,
        request: Request,
        current: Actor,
        review_id: Annotated[str, Path(alias="reviewId", pattern=r"^REV-[A-Za-z0-9-]+$")],
    ) -> dict[str, object]:
        bundle = service.rerun(
            current,
            review_id,
            reason=payload.reason,
            review_types=tuple(payload.reviewTypes) if payload.reviewTypes else None,
            trace_id=request.state.trace_id,
        )
        return {
            "newReviewId": bundle.review.review_id,
            "previousReviewId": review_id,
            "reviewStatus": bundle.review.status,
            "jobId": bundle.job.job_id,
        }
