"""HTTP boundary for deterministic M6 support services."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.support import SupportService


def install_support_routes(
    router: APIRouter,
    service: SupportService,
    actor_dependency: Callable[..., Awaitable[CurrentUser]],
) -> None:
    Actor = Annotated[CurrentUser, Depends(actor_dependency)]

    @router.get("/reviews/{reviewId}/suggestions", operation_id="listReviewSuggestions")
    async def suggestions(
        request: Request,
        current: Actor,
        review_id: Annotated[str, Path(alias="reviewId")],
    ) -> list[dict[str, object]]:
        return service.list_suggestions(current, review_id, request.state.trace_id)

    @router.patch("/suggestions/{suggestionId}/decision", operation_id="recordSuggestionDecision")
    async def decision(
        request: Request,
        current: Actor,
        suggestion_id: Annotated[str, Path(alias="suggestionId")],
    ) -> dict[str, object]:
        return service.decide(current, suggestion_id, await request.json(), request.state.trace_id)

    @router.post("/qa/questions", operation_id="askComplianceQuestion")
    async def question(request: Request, current: Actor) -> dict[str, object]:
        return service.question(current, await request.json(), request.state.trace_id)

    @router.get("/qa/questions", operation_id="listComplianceQuestions")
    async def questions(current: Actor) -> list[dict[str, object]]:
        return service.list_questions(current)

    @router.post("/reviews/{reviewId}/opinion-drafts", operation_id="createOpinionDraft")
    async def create_draft(
        request: Request,
        current: Actor,
        review_id: Annotated[str, Path(alias="reviewId")],
    ) -> dict[str, object]:
        return service.create_draft(
            current, review_id, await request.json(), request.state.trace_id
        )

    @router.get("/reviews/{reviewId}/opinion-drafts", operation_id="listOpinionDrafts")
    async def list_drafts(
        request: Request,
        current: Actor,
        review_id: Annotated[str, Path(alias="reviewId")],
    ) -> list[dict[str, object]]:
        return service.drafts_for(current, review_id, request.state.trace_id)

    @router.patch("/opinion-drafts/{draftId}", operation_id="updateOpinionDraft")
    async def update_draft(
        request: Request,
        current: Actor,
        draft_id: Annotated[str, Path(alias="draftId")],
    ) -> dict[str, object]:
        return service.update_draft(current, draft_id, await request.json(), request.state.trace_id)

    @router.post("/reviews/{reviewId}/reports", operation_id="createReviewReport")
    async def create_report(
        request: Request,
        current: Actor,
        review_id: Annotated[str, Path(alias="reviewId")],
    ) -> dict[str, object]:
        return service.create_report(
            current, review_id, await request.json(), request.state.trace_id
        )

    @router.get("/reports/{reportId}", operation_id="getReviewReport")
    async def get_report(
        request: Request,
        current: Actor,
        report_id: Annotated[str, Path(alias="reportId")],
    ) -> dict[str, object]:
        return service.get_report(current, report_id, request.state.trace_id)

    @router.get("/reports/{reportId}/download", operation_id="downloadReviewReport")
    async def download_report(
        request: Request,
        current: Actor,
        report_id: Annotated[str, Path(alias="reportId")],
    ) -> Response:
        content, report_format = service.download_report(current, report_id, request.state.trace_id)
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{report_id}.{report_format.lower()}"'
            },
        )

    @router.post(
        "/advertisements/{advertisementId}/comparisons",
        operation_id="createAdvertisementComparison",
    )
    async def create_comparison(
        request: Request,
        current: Actor,
        advertisement_id: Annotated[str, Path(alias="advertisementId")],
    ) -> dict[str, object]:
        return service.create_comparison(
            current, advertisement_id, await request.json(), request.state.trace_id
        )

    @router.get("/comparisons/{comparisonId}", operation_id="getAdvertisementComparison")
    async def get_comparison(
        request: Request,
        current: Actor,
        comparison_id: Annotated[str, Path(alias="comparisonId")],
    ) -> dict[str, object]:
        return service.get_comparison(current, comparison_id, request.state.trace_id)
