"""Thin HTTP routes for the five frozen M7 Validation operations."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.multipart import MultipartError, parse_multipart
from nh_ad_backend.services import ServiceError
from nh_ad_backend.validation import (
    ValidationService,
    dataset_response,
    evaluation_response,
    judgment_response,
)


MetricCode = Literal[
    "REQUIRED_PHRASE_ACCURACY",
    "MISLEADING_EXPRESSION_ACCURACY",
    "EVIDENCE_PRECISION",
    "HUMAN_AGREEMENT_RATE",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class JudgmentInput(ContractModel):
    target_text: str = Field(alias="targetText", min_length=1)
    review_type: Literal[
        "REQUIRED_PHRASE",
        "INTEREST_RATE",
        "MISLEADING_EXPRESSION",
        "PRODUCT_CONSISTENCY",
        "VISIBILITY",
        "OCR_QUALITY",
    ] = Field(alias="reviewType")
    expected_status: Literal["APPROPRIATE", "NEEDS_REVISION", "NEEDS_CONFIRMATION"] = Field(
        alias="expectedStatus"
    )
    risk_level: Literal["HIGH", "MEDIUM", "LOW", "CHECK_REQUIRED"] | None = Field(
        None, alias="riskLevel"
    )
    comment: str | None = None
    excluded: bool = False
    exclude_reason_code: (
        Literal[
            "OCR_UNREADABLE",
            "PRODUCT_CONDITION_AMBIGUOUS",
            "REFERENCE_NOT_PROVIDED",
            "SOURCE_FILE_CORRUPTED",
            "LABEL_UNCLEAR",
            "DUPLICATE_SAMPLE",
            "OUT_OF_SCOPE",
        ]
        | None
    ) = Field(None, alias="excludeReasonCode")
    exclude_reason_detail: str | None = Field(None, alias="excludeReasonDetail")


class CreateJudgmentsRequest(ContractModel):
    judgments: list[JudgmentInput] = Field(min_length=1)


class CreateEvaluationRequest(ContractModel):
    datasetIds: list[str] = Field(min_length=1)  # noqa: N815 - frozen JSON contract
    metrics: list[MetricCode] = Field(min_length=1, max_length=4)
    excludeInvalidSamples: bool  # noqa: N815 - frozen JSON contract
    reviewSelectionPolicy: Literal["LATEST_COMPLETED"]  # noqa: N815 - frozen JSON contract


def install_validation_routes(router: APIRouter, service: ValidationService, actor: object) -> None:
    from nh_ad_backend.api import error_models

    Actor = Annotated[CurrentUser, Depends(actor)]

    @router.get(
        "/validation/datasets",
        operation_id="listValidationDatasets",
        responses=error_models(401, 403),
    )
    async def list_validation_datasets(
        request: Request,
        current: Actor,
        page: Annotated[int, Query(ge=0)] = 0,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        items, total = service.list_datasets(current, page, size, request.state.trace_id)
        return {
            "items": [dataset_response(value) for value in items],
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": (total + size - 1) // size,
        }

    @router.post(
        "/validation/datasets",
        status_code=201,
        operation_id="createValidationDataset",
        responses=error_models(400, 401, 403, 409),
    )
    async def create_validation_dataset(request: Request, current: Actor) -> dict[str, object]:
        try:
            form = await parse_multipart(
                request,
                extra_fields=frozenset(
                    {
                        "datasetName",
                        "humanReviewComment",
                        "labelJson",
                        "excluded",
                        "excludeReasonCode",
                        "excludeReasonDetail",
                    }
                ),
                extra_files=frozenset({"productConditionFile"}),
            )
        except MultipartError as exc:
            raise ServiceError(exc.status_code, exc.code, str(exc)) from exc
        advertisement_files = form.files.get("advertisementFile", [])
        product_condition_files = form.files.get("productConditionFile", [])
        if len(advertisement_files) != 1 or len(product_condition_files) > 1:
            raise ServiceError(400, "BAD_REQUEST", "검증 파일 첨부값을 확인해 주세요.")
        advertisement = advertisement_files[0]
        product_condition = product_condition_files[0] if product_condition_files else None
        excluded_text = form.fields.get("excluded", "false").casefold()
        if excluded_text not in {"true", "false"}:
            raise ServiceError(400, "BAD_REQUEST", "excluded 값을 확인해 주세요.")
        value = service.create_dataset(
            current,
            dataset_name=form.fields.get("datasetName", ""),
            product_group=form.fields.get("productGroup", ""),
            advertisement_type=form.fields.get("advertisementType", ""),
            advertisement_file={
                "fileName": advertisement.file_name,
                "contentType": advertisement.content_type,
                "content": advertisement.stream.getvalue(),
            },
            product_condition_file=(
                {
                    "fileName": product_condition.file_name,
                    "contentType": product_condition.content_type,
                    "content": product_condition.stream.getvalue(),
                }
                if product_condition
                else None
            ),
            human_review_comment=form.fields.get("humanReviewComment"),
            label_json=form.fields.get("labelJson"),
            excluded=excluded_text == "true",
            exclude_reason_code=form.fields.get("excludeReasonCode"),
            exclude_reason_detail=form.fields.get("excludeReasonDetail"),
            trace_id=request.state.trace_id,
        )
        return dataset_response(value)

    @router.post(
        "/validation/datasets/{datasetId}/judgments",
        status_code=201,
        operation_id="createValidationJudgments",
        responses=error_models(400, 401, 403, 404, 409),
    )
    async def create_validation_judgments(
        dataset_id: Annotated[str, Path(alias="datasetId", pattern=r"^DATASET-[A-Za-z0-9-]+$")],
        payload: CreateJudgmentsRequest,
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        values = service.create_judgments(
            current,
            dataset_id,
            [value.model_dump(by_alias=True) for value in payload.judgments],
            request.state.trace_id,
        )
        return {"datasetId": dataset_id, "judgments": [judgment_response(v) for v in values]}

    @router.post(
        "/validation/evaluations",
        status_code=201,
        operation_id="createValidationEvaluation",
        responses=error_models(400, 401, 403, 409),
    )
    async def create_validation_evaluation(
        payload: CreateEvaluationRequest, request: Request, current: Actor
    ) -> dict[str, object]:
        value = service.create_evaluation(
            current,
            dataset_ids=payload.datasetIds,
            metrics=payload.metrics,
            exclude_invalid_samples=payload.excludeInvalidSamples,
            review_selection_policy=payload.reviewSelectionPolicy,
            trace_id=request.state.trace_id,
        )
        return evaluation_response(value)

    @router.get(
        "/validation/evaluations/{evaluationId}",
        operation_id="getValidationEvaluation",
        responses=error_models(401, 403, 404),
    )
    async def get_validation_evaluation(
        evaluation_id: Annotated[str, Path(alias="evaluationId", pattern=r"^EVAL-[A-Za-z0-9-]+$")],
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        return evaluation_response(
            service.get_evaluation(current, evaluation_id, request.state.trace_id)
        )
