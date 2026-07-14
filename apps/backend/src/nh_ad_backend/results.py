"""M5 review-result read model and scoped service."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine, text

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.reviews import ReviewService
from nh_ad_backend.services import ServiceError


@dataclass(frozen=True)
class ResultEvidence:
    evidence_id: str
    evidence_chunk_id: str | None
    standard_version_id: str
    evidence_type: str
    title: str
    article_no: str | None
    matched_text: str
    rank_no: int
    relevance_score: float
    match_source: str


@dataclass(frozen=True)
class ResultAnnotation:
    annotation_id: str
    review_item_id: str
    file_id: str
    file_type: str
    review_type: str
    risk_level: str
    target_text: str
    display_mode: str
    status: str
    location_confidence: float | None
    confidence_policy_version: str
    display_reason: str
    page_no: int | None
    coordinate: dict[str, object] | None
    text_block_id: str | None = None
    text_path: str | None = None
    raw_start_offset: int | None = None
    raw_end_offset: int | None = None
    normalized_start_offset: int | None = None
    normalized_end_offset: int | None = None
    matched_text: str | None = None


@dataclass(frozen=True)
class ResultItem:
    review_item_id: str
    review_id: str
    review_type: str
    target_text: str
    result_status: str
    risk_level: str
    risk_policy_version: str
    risk_reason_codes: tuple[str, ...]
    risk_score_detail: dict[str, object]
    evidence_status: str
    evidence_failure_code: str | None
    reason: str
    recommendation: str | None
    source_engine: str
    source_version: str
    page_no: int | None
    evidences: tuple[ResultEvidence, ...] = ()
    annotation: ResultAnnotation | None = None


class ResultRepository(Protocol):
    def list_items(self, review_id: str) -> list[ResultItem]: ...
    def get_item(self, review_id: str, item_id: str) -> ResultItem | None: ...
    def annotations(self, review_id: str) -> list[ResultAnnotation]: ...


class InMemoryResultRepository:
    def __init__(self, items: tuple[ResultItem, ...] = ()) -> None:
        self._items = list(items)

    def add(self, *items: ResultItem) -> None:
        self._items.extend(items)

    def list_items(self, review_id: str) -> list[ResultItem]:
        return [item for item in self._items if item.review_id == review_id]

    def get_item(self, review_id: str, item_id: str) -> ResultItem | None:
        return next(
            (
                item
                for item in self._items
                if item.review_id == review_id and item.review_item_id == item_id
            ),
            None,
        )

    def annotations(self, review_id: str) -> list[ResultAnnotation]:
        return [
            item.annotation
            for item in self._items
            if item.review_id == review_id and item.annotation is not None
        ]


class PostgresResultRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_items(self, review_id: str) -> list[ResultItem]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM app.review_items WHERE review_id=:review_id "
                    "ORDER BY CASE risk_level WHEN 'HIGH' THEN 1 WHEN 'CHECK_REQUIRED' THEN 2 "
                    "WHEN 'MEDIUM' THEN 3 ELSE 4 END, created_at, review_item_id"
                ),
                {"review_id": review_id},
            ).mappings()
            return [self._item(connection, row) for row in rows]

    def get_item(self, review_id: str, item_id: str) -> ResultItem | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM app.review_items "
                        "WHERE review_id=:review_id AND review_item_id=:item_id"
                    ),
                    {"review_id": review_id, "item_id": item_id},
                )
                .mappings()
                .first()
            )
            return self._item(connection, row) if row else None

    def annotations(self, review_id: str) -> list[ResultAnnotation]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT a.*,ri.target_text,af.file_type
                      FROM app.annotations a
                      JOIN app.review_items ri USING (review_item_id)
                      JOIN app.advertisement_files af USING (file_id)
                     WHERE a.review_id=:review_id
                     ORDER BY a.display_order,a.annotation_id
                """),
                {"review_id": review_id},
            ).mappings()
            return [self._annotation(row) for row in rows]

    def _item(self, connection: object, row: object) -> ResultItem:
        evidence_rows = connection.execute(  # type: ignore[attr-defined]
            text("""
                SELECT rie.*,e.evidence_type,e.title,e.article_no
                  FROM app.review_item_evidences rie
                  JOIN rag.evidences e USING (evidence_id)
                 WHERE rie.review_item_id=:item_id ORDER BY rie.rank_no
            """),
            {"item_id": row["review_item_id"]},  # type: ignore[index]
        ).mappings()
        evidences = tuple(
            ResultEvidence(
                value["evidence_id"],
                value["evidence_chunk_id"],
                value["standard_version_id"],
                value["evidence_type"],
                value["title"],
                value["article_no"],
                value["matched_text"] or "",
                value["rank_no"],
                float(value["relevance_score"]),
                value["match_source"],
            )
            for value in evidence_rows
        )
        annotation_row = (
            connection.execute(  # type: ignore[attr-defined]
                text("""
                SELECT a.*,ri.target_text,af.file_type
                  FROM app.annotations a
                  JOIN app.review_items ri USING (review_item_id)
                  JOIN app.advertisement_files af USING (file_id)
                 WHERE a.review_item_id=:item_id ORDER BY a.display_order LIMIT 1
            """),
                {"item_id": row["review_item_id"]},  # type: ignore[index]
            )
            .mappings()
            .first()
        )
        return ResultItem(
            row["review_item_id"],  # type: ignore[index]
            row["review_id"],  # type: ignore[index]
            row["review_type"],  # type: ignore[index]
            row["target_text"] or "",  # type: ignore[index]
            row["result_status"],  # type: ignore[index]
            row["risk_level"],  # type: ignore[index]
            row["risk_policy_version"],  # type: ignore[index]
            tuple(row["risk_reason_codes"]),  # type: ignore[index]
            dict(row["risk_score_detail"]),  # type: ignore[index]
            row["evidence_status"],  # type: ignore[index]
            row["evidence_failure_code"],  # type: ignore[index]
            row["reason"],  # type: ignore[index]
            row["recommendation"],  # type: ignore[index]
            row["engine_type"],  # type: ignore[index]
            row["engine_version"],  # type: ignore[index]
            row["page_no"],  # type: ignore[index]
            evidences,
            self._annotation(annotation_row) if annotation_row else None,
        )

    @staticmethod
    def _annotation(row: object) -> ResultAnnotation:
        coordinate = None
        if row["source_width"] is not None:  # type: ignore[index]
            coordinate = {
                "sourceWidth": float(row["source_width"]),  # type: ignore[index]
                "sourceHeight": float(row["source_height"]),  # type: ignore[index]
                "sourceUnit": row["source_unit"],  # type: ignore[index]
                "x": float(row["x"]),  # type: ignore[index]
                "y": float(row["y"]),  # type: ignore[index]
                "width": float(row["width"]),  # type: ignore[index]
                "height": float(row["height"]),  # type: ignore[index]
                "normalizedX": float(row["normalized_x"]),  # type: ignore[index]
                "normalizedY": float(row["normalized_y"]),  # type: ignore[index]
                "normalizedWidth": float(row["normalized_width"]),  # type: ignore[index]
                "normalizedHeight": float(row["normalized_height"]),  # type: ignore[index]
                "rotation": float(row["rotation"] or 0),  # type: ignore[index]
                "coordinateConfidence": float(row["coordinate_confidence"]),  # type: ignore[index]
            }
        return ResultAnnotation(
            row["annotation_id"],  # type: ignore[index]
            row["review_item_id"],  # type: ignore[index]
            row["file_id"],  # type: ignore[index]
            row["file_type"],  # type: ignore[index]
            row["review_type"],  # type: ignore[index]
            row["risk_level"],  # type: ignore[index]
            row["target_text"] or "",  # type: ignore[index]
            row["annotation_display_mode"],  # type: ignore[index]
            row["annotation_status"],  # type: ignore[index]
            float(row["location_confidence"]) if row["location_confidence"] is not None else None,  # type: ignore[index]
            row["confidence_policy_version"],  # type: ignore[index]
            row["display_reason"],  # type: ignore[index]
            row["page_no"],  # type: ignore[index]
            coordinate,
            row["text_block_id"],  # type: ignore[index]
            row["text_path"],  # type: ignore[index]
            row["raw_start_offset"],  # type: ignore[index]
            row["raw_end_offset"],  # type: ignore[index]
            row["normalized_start_offset"],  # type: ignore[index]
            row["normalized_end_offset"],  # type: ignore[index]
            row["matched_text"],  # type: ignore[index]
        )


class ResultService:
    def __init__(self, repository: ResultRepository, reviews: ReviewService) -> None:
        self.repository = repository
        self.reviews = reviews

    def _review(self, actor: CurrentUser, review_id: str, trace_id: str) -> object:
        return self.reviews.status(actor, review_id, trace_id).review

    def summary(self, actor: CurrentUser, review_id: str, trace_id: str) -> dict[str, object]:
        review = self._review(actor, review_id, trace_id)
        items = self.repository.list_items(review_id)
        if not items or review.completed_at is None:  # type: ignore[attr-defined]
            raise ServiceError(404, "REVIEW_RESULT_NOT_FOUND", "검토 결과를 찾을 수 없습니다.")
        by_type: dict[str, list[ResultItem]] = {}
        for item in items:
            by_type.setdefault(item.review_type, []).append(item)
        severity = {"HIGH": 4, "CHECK_REQUIRED": 3, "MEDIUM": 2, "LOW": 1}
        ordered = sorted(items, key=lambda item: severity[item.risk_level], reverse=True)
        return {
            "reviewId": review_id,
            "advertisementId": review.advertisement_id,  # type: ignore[attr-defined]
            "standardEffectiveDate": review.standard_effective_date,  # type: ignore[attr-defined]
            "standardVersionIds": list(review.standard_version_ids),  # type: ignore[attr-defined]
            "overallRiskLevel": ordered[0].risk_level,
            "totalItemCount": len(items),
            "needsRevisionCount": sum(item.result_status == "NEEDS_REVISION" for item in items),
            "needsConfirmationCount": sum(
                item.result_status == "NEEDS_CONFIRMATION" for item in items
            ),
            "reviewTypeSummary": [
                {
                    "reviewType": review_type,
                    "totalCount": len(values),
                    "needsRevisionCount": sum(
                        item.result_status == "NEEDS_REVISION" for item in values
                    ),
                    "needsConfirmationCount": sum(
                        item.result_status == "NEEDS_CONFIRMATION" for item in values
                    ),
                }
                for review_type, values in sorted(by_type.items())
            ],
            "topRisks": [
                {
                    "reviewItemId": item.review_item_id,
                    "riskLevel": item.risk_level,
                    "riskPolicyVersion": item.risk_policy_version,
                    "riskReasonCodes": list(item.risk_reason_codes),
                    "targetText": item.target_text,
                    "reason": item.reason,
                    "evidenceStatus": item.evidence_status,
                }
                for item in ordered[:5]
            ],
            "completedAt": review.completed_at,  # type: ignore[attr-defined]
        }

    def items(
        self,
        actor: CurrentUser,
        review_id: str,
        trace_id: str,
        *,
        review_type: str | None,
        risk_level: str | None,
        result_status: str | None,
        evidence_required: bool | None,
        page: int,
        size: int,
    ) -> dict[str, object]:
        self._review(actor, review_id, trace_id)
        values = self.repository.list_items(review_id)
        if review_type:
            values = [item for item in values if item.review_type == review_type]
        if risk_level:
            values = [item for item in values if item.risk_level == risk_level]
        if result_status:
            values = [item for item in values if item.result_status == result_status]
        if evidence_required is not None:
            values = [
                item
                for item in values
                if (item.evidence_status != "NOT_REQUIRED") is evidence_required
            ]
        total = len(values)
        return {
            "contents": [self._summary(item) for item in values[(page - 1) * size : page * size]],
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": math.ceil(total / size),
        }

    def item(
        self, actor: CurrentUser, review_id: str, item_id: str, trace_id: str
    ) -> dict[str, object]:
        self._review(actor, review_id, trace_id)
        item = self.repository.get_item(review_id, item_id)
        if item is None:
            raise ServiceError(404, "NOT_FOUND", "요청한 검토 항목을 찾을 수 없습니다.")
        return {
            **self._summary(item),
            "riskRationale": {
                "riskLevel": item.risk_level,
                "policyVersion": item.risk_policy_version,
                "reasonCodes": list(item.risk_reason_codes),
                "scoreDetail": item.risk_score_detail,
            },
            "evidences": [self._evidence(value) for value in item.evidences],
            "recommendation": item.recommendation,
            "annotation": self._annotation(item.annotation) if item.annotation else None,
        }

    def annotation_collection(
        self,
        actor: CurrentUser,
        review_id: str,
        trace_id: str,
        *,
        page_no: int | None,
        review_type: str | None,
        risk_level: str | None,
    ) -> dict[str, object]:
        review = self._review(actor, review_id, trace_id)
        values = self.repository.annotations(review_id)
        if page_no is not None:
            values = [value for value in values if value.page_no == page_no]
        if review_type:
            values = [value for value in values if value.review_type == review_type]
        if risk_level:
            values = [value for value in values if value.risk_level == risk_level]
        advertisement = self.reviews.advertisements.get(
            actor,
            review.advertisement_id,  # type: ignore[attr-defined]
            trace_id,
        )
        first_file = advertisement.files[0] if advertisement.files else None
        return {
            "reviewId": review_id,
            "fileId": values[0].file_id if values else first_file.file_id if first_file else "",
            "fileType": values[0].file_type
            if values
            else first_file.file_type
            if first_file
            else "UNKNOWN",
            "pageNo": page_no,
            "annotations": [self._annotation(value) for value in values],
        }

    @staticmethod
    def _summary(item: ResultItem) -> dict[str, object]:
        return {
            "reviewItemId": item.review_item_id,
            "reviewType": item.review_type,
            "targetText": item.target_text,
            "resultStatus": item.result_status,
            "riskLevel": item.risk_level,
            "riskPolicyVersion": item.risk_policy_version,
            "riskReasonCodes": list(item.risk_reason_codes),
            "reason": item.reason,
            "evidenceStatus": item.evidence_status,
            "evidenceFailureCode": item.evidence_failure_code,
            "evidenceCount": len(item.evidences),
            "pageNo": item.page_no,
            "hasAnnotation": item.annotation is not None,
            "sourceEngine": item.source_engine,
            "sourceVersion": item.source_version,
        }

    @staticmethod
    def _evidence(value: ResultEvidence) -> dict[str, object]:
        return {
            "evidenceId": value.evidence_id,
            "evidenceChunkId": value.evidence_chunk_id,
            "standardVersionId": value.standard_version_id,
            "evidenceType": value.evidence_type,
            "title": value.title,
            "articleNo": value.article_no,
            "matchedText": value.matched_text,
            "rankNo": value.rank_no,
            "relevanceScore": value.relevance_score,
            "matchSource": value.match_source,
        }

    @staticmethod
    def _annotation(value: ResultAnnotation) -> dict[str, object]:
        return {
            "annotationId": value.annotation_id,
            "reviewItemId": value.review_item_id,
            "reviewType": value.review_type,
            "riskLevel": value.risk_level,
            "targetText": value.target_text,
            "annotationDisplayMode": value.display_mode,
            "annotationStatus": value.status,
            "locationConfidence": value.location_confidence,
            "confidencePolicyVersion": value.confidence_policy_version,
            "displayReason": value.display_reason,
            "pageNo": value.page_no,
            "coordinate": value.coordinate,
            "textBlockId": value.text_block_id,
            "textPath": value.text_path,
            "rawStartOffset": value.raw_start_offset,
            "rawEndOffset": value.raw_end_offset,
            "normalizedStartOffset": value.normalized_start_offset,
            "normalizedEndOffset": value.normalized_end_offset,
            "matchedText": value.matched_text,
        }
