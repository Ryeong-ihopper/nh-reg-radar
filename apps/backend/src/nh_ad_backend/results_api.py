"""HTTP handlers for the frozen M5 review-result contract."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.results import ResultService


ReviewType = Literal[
    "REQUIRED_PHRASE",
    "INTEREST_RATE",
    "MISLEADING_EXPRESSION",
    "PRODUCT_CONSISTENCY",
    "VISIBILITY",
    "OCR_QUALITY",
]
RiskLevel = Literal["HIGH", "MEDIUM", "LOW", "CHECK_REQUIRED"]
ResultStatus = Literal["APPROPRIATE", "NEEDS_REVISION", "NEEDS_CONFIRMATION"]


def install_result_routes(
    router: APIRouter,
    service: ResultService,
    actor_dependency: object,
) -> None:
    Actor = Annotated[CurrentUser, Depends(actor_dependency)]
    ReviewId = Annotated[str, Path(alias="reviewId", pattern=r"^REV-[A-Za-z0-9-]+$")]

    @router.get("/reviews/{reviewId}/summary", operation_id="getReviewSummary")
    async def summary(request: Request, current: Actor, review_id: ReviewId) -> dict[str, object]:
        return service.summary(current, review_id, request.state.trace_id)

    @router.get("/reviews/{reviewId}/items", operation_id="listReviewItems")
    async def items(
        request: Request,
        current: Actor,
        review_id: ReviewId,
        review_type: Annotated[ReviewType | None, Query(alias="reviewType")] = None,
        risk_level: Annotated[RiskLevel | None, Query(alias="riskLevel")] = None,
        result_status: Annotated[ResultStatus | None, Query(alias="resultStatus")] = None,
        include_appropriate: Annotated[bool, Query(alias="includeAppropriate")] = False,
        evidence_required: Annotated[bool | None, Query(alias="evidenceRequired")] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        return service.items(
            current,
            review_id,
            request.state.trace_id,
            review_type=review_type,
            risk_level=risk_level,
            result_status=result_status,
            include_appropriate=include_appropriate,
            evidence_required=evidence_required,
            page=page,
            size=size,
        )

    @router.get("/reviews/{reviewId}/items/{reviewItemId}", operation_id="getReviewItem")
    async def item(
        request: Request,
        current: Actor,
        review_id: ReviewId,
        review_item_id: Annotated[str, Path(alias="reviewItemId", pattern=r"^ITEM-[A-Za-z0-9-]+$")],
    ) -> dict[str, object]:
        return service.item(current, review_id, review_item_id, request.state.trace_id)

    @router.get("/reviews/{reviewId}/annotations", operation_id="listReviewAnnotations")
    async def annotations(
        request: Request,
        current: Actor,
        review_id: ReviewId,
        page_no: Annotated[int | None, Query(alias="pageNo", ge=1)] = None,
        review_type: Annotated[ReviewType | None, Query(alias="reviewType")] = None,
        risk_level: Annotated[RiskLevel | None, Query(alias="riskLevel")] = None,
    ) -> dict[str, object]:
        return service.annotation_collection(
            current,
            review_id,
            request.state.trace_id,
            page_no=page_no,
            review_type=review_type,
            risk_level=risk_level,
        )
