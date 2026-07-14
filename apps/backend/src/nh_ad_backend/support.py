"""Deterministic M6 support behavior with durable repository boundaries."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import Engine, text

from nh_ad_backend.domain import AuditEvent, CurrentUser
from nh_ad_backend.reviews import ReviewService
from nh_ad_backend.services import AdvertisementService, ServiceError


AuditSink = Callable[[AuditEvent], None]


def _iso(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SupportRepository(Protocol):
    def next_identifier(self, prefix: str) -> str: ...
    def list_suggestions(self, review_id: str) -> list[dict[str, Any]]: ...
    def get_suggestion(self, suggestion_id: str) -> dict[str, Any] | None: ...
    def save_decision(self, decision: dict[str, Any]) -> None: ...
    def save_question(self, actor: CurrentUser, question: dict[str, Any]) -> None: ...
    def list_questions(self, actor: CurrentUser) -> list[dict[str, Any]]: ...
    def save_draft(self, draft: dict[str, Any]) -> None: ...
    def list_drafts(self, review_id: str) -> list[dict[str, Any]]: ...
    def get_draft(self, draft_id: str) -> dict[str, Any] | None: ...
    def update_draft(self, draft: dict[str, Any]) -> None: ...
    def save_report(self, report: dict[str, Any]) -> None: ...
    def get_report(self, report_id: str) -> dict[str, Any] | None: ...
    def save_comparison(self, comparison: dict[str, Any]) -> None: ...
    def get_comparison(self, comparison_id: str) -> dict[str, Any] | None: ...


class InMemorySupportRepository:
    """Thread-safe deterministic support store shared across service restarts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.suggestions: dict[str, dict[str, Any]] = {
            "SUG-0001": {
                "suggestionId": "SUG-0001",
                "reviewId": "REV-0001",
                "reviewItemId": "ITEM-0001",
                "originalText": "국내 최고 수준의 혜택",
                "suggestedText": "조건 충족 시 우대 혜택을 제공받을 수 있습니다.",
                "suggestionReason": "확정적 표현을 조건부 표현으로 완화",
                "evidenceIds": ["EVD-0001"],
                "decisionStatus": "PENDING",
            }
        }
        self.decisions: list[dict[str, Any]] = []
        self.questions: list[dict[str, Any]] = []
        self.drafts: dict[str, dict[str, Any]] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self.comparisons: dict[str, dict[str, Any]] = {}
        self._counters: dict[str, int] = {"SUG": 1}

    def next_identifier(self, prefix: str) -> str:
        with self._lock:
            self._counters[prefix] = self._counters.get(prefix, 0) + 1
            return f"{prefix}-{self._counters[prefix]:04d}"

    def list_suggestions(self, review_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                deepcopy(value)
                for value in self.suggestions.values()
                if value["reviewId"] == review_id
            ]

    def get_suggestion(self, suggestion_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.suggestions.get(suggestion_id)
            return deepcopy(value) if value else None

    def save_decision(self, decision: dict[str, Any]) -> None:
        with self._lock:
            suggestion = self.suggestions[decision["suggestionId"]]
            suggestion["decisionStatus"] = decision["decisionStatus"]
            self.decisions.append(deepcopy(decision))

    def save_question(self, actor: CurrentUser, question: dict[str, Any]) -> None:
        with self._lock:
            self.questions.append({**deepcopy(question), "userId": actor.user_id})

    def list_questions(self, actor: CurrentUser) -> list[dict[str, Any]]:
        with self._lock:
            return [
                deepcopy(value)
                for value in self.questions
                if value["userId"] == actor.user_id
            ]

    def save_draft(self, draft: dict[str, Any]) -> None:
        with self._lock:
            self.drafts[draft["draftId"]] = deepcopy(draft)

    def list_drafts(self, review_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                deepcopy(value)
                for value in self.drafts.values()
                if value["reviewId"] == review_id
            ]

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.drafts.get(draft_id)
            return deepcopy(value) if value else None

    def update_draft(self, draft: dict[str, Any]) -> None:
        self.save_draft(draft)

    def save_report(self, report: dict[str, Any]) -> None:
        with self._lock:
            self.reports[report["reportId"]] = deepcopy(report)

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.reports.get(report_id)
            return deepcopy(value) if value else None

    def save_comparison(self, comparison: dict[str, Any]) -> None:
        with self._lock:
            self.comparisons[comparison["comparisonId"]] = deepcopy(comparison)

    def get_comparison(self, comparison_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.comparisons.get(comparison_id)
            return deepcopy(value) if value else None


class PostgresSupportRepository:
    """SQL implementation over the frozen 0006 M6 owner tables."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def next_identifier(self, prefix: str) -> str:
        return f"{prefix}-{secrets.token_hex(12).upper()}"

    @staticmethod
    def _suggestion(row: Any) -> dict[str, Any]:
        return {
            "suggestionId": row["suggestion_id"],
            "reviewId": row["review_id"],
            "reviewItemId": row["review_item_id"],
            "originalText": row["original_text"],
            "suggestedText": row["suggested_text"],
            "suggestionReason": row["suggestion_reason"],
            "evidenceIds": list(row["evidence_ids"] or []),
            "decisionStatus": row["decision_status"],
        }

    def list_suggestions(self, review_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM app.suggestions WHERE review_id=:review_id "
                    "ORDER BY created_at,suggestion_id"
                ),
                {"review_id": review_id},
            ).mappings().all()
        return [self._suggestion(row) for row in rows]

    def get_suggestion(self, suggestion_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM app.suggestions WHERE suggestion_id=:suggestion_id"),
                {"suggestion_id": suggestion_id},
            ).mappings().first()
        return self._suggestion(row) if row else None

    def save_decision(self, decision: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO app.suggestion_decisions
                    (suggestion_decision_id,suggestion_id,decision_status,final_text,comment,
                     decided_by,decided_at)
                    VALUES (:decision_id,:suggestion_id,:status,:final_text,:comment,:actor,:decided_at)
                """),
                {
                    "decision_id": uuid4(),
                    "suggestion_id": decision["suggestionId"],
                    "status": decision["decisionStatus"],
                    "final_text": decision["finalText"],
                    "comment": decision["comment"],
                    "actor": decision["decidedBy"],
                    "decided_at": decision["decidedAt"],
                },
            )
            connection.execute(
                text(
                    "UPDATE app.suggestions SET decision_status=:status "
                    "WHERE suggestion_id=:suggestion_id"
                ),
                {
                    "status": decision["decisionStatus"],
                    "suggestion_id": decision["suggestionId"],
                },
            )

    def save_question(self, actor: CurrentUser, question: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO rag.qa_sessions
                    (qa_session_id,user_id,product_group,advertisement_type,standard_effective_date,
                     standard_version_ids,title,created_at)
                    VALUES (:session_id,:user_id,:product_group,:advertisement_type,:effective_date,
                            CAST(:versions AS jsonb),:title,:created_at)
                """),
                {
                    "session_id": question["sessionId"],
                    "user_id": actor.user_id,
                    "product_group": question["productGroup"],
                    "advertisement_type": question["advertisementType"],
                    "effective_date": question["standardEffectiveDate"],
                    "versions": json.dumps(question["standardVersionIds"]),
                    "title": question["question"][:500],
                    "created_at": question["createdAt"],
                },
            )
            answer = question["answer"]
            connection.execute(
                text("""
                    INSERT INTO rag.qa_messages
                    (qa_message_id,qa_session_id,question,answer_summary,answer_detail,
                     needs_human_review,suggested_phrases,raw_response_json,created_at)
                    VALUES (:message_id,:session_id,:question,:summary,:detail,:human,
                            CAST(:phrases AS jsonb),CAST(:raw AS jsonb),:created_at)
                """),
                {
                    "message_id": answer["qaId"],
                    "session_id": question["sessionId"],
                    "question": question["question"],
                    "summary": answer["answerSummary"],
                    "detail": answer["answerDetail"],
                    "human": answer["needsHumanReview"],
                    "phrases": json.dumps(answer["suggestedPhrases"]),
                    "raw": json.dumps(answer),
                    "created_at": question["createdAt"],
                },
            )

    def list_questions(self, actor: CurrentUser) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT m.raw_response_json
                      FROM rag.qa_messages m JOIN rag.qa_sessions s USING (qa_session_id)
                     WHERE s.user_id=:user_id ORDER BY m.created_at,m.qa_message_id
                """),
                {"user_id": actor.user_id},
            ).scalars().all()
        return [dict(value) for value in rows]

    @staticmethod
    def _draft(row: Any) -> dict[str, Any]:
        return {
            "draftId": row["draft_id"],
            "reviewId": row["review_id"],
            "draftContent": row["draft_content"],
            "finalContent": row["final_content"],
            "includedReviewItemIds": list(row["included_review_item_ids"] or []),
            "createdAt": _iso(row["created_at"]),
            "updatedAt": _iso(row["updated_at"]),
        }

    def save_draft(self, draft: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO app.opinion_drafts
                    (draft_id,review_id,template_type,draft_content,final_content,
                     included_review_item_ids,additional_instruction,created_at,created_by)
                    VALUES (:draft_id,:review_id,:template_type,:draft_content,NULL,
                            CAST(:item_ids AS jsonb),:instruction,:created_at,:created_by)
                """),
                {
                    "draft_id": draft["draftId"],
                    "review_id": draft["reviewId"],
                    "template_type": draft["templateType"],
                    "draft_content": draft["draftContent"],
                    "item_ids": json.dumps(draft["includedReviewItemIds"]),
                    "instruction": draft["additionalInstruction"],
                    "created_at": draft["createdAt"],
                    "created_by": draft["createdBy"],
                },
            )

    def list_drafts(self, review_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM app.opinion_drafts WHERE review_id=:review_id "
                    "ORDER BY created_at,draft_id"
                ),
                {"review_id": review_id},
            ).mappings().all()
        return [self._draft(row) for row in rows]

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM app.opinion_drafts WHERE draft_id=:draft_id"),
                {"draft_id": draft_id},
            ).mappings().first()
        return self._draft(row) if row else None

    def update_draft(self, draft: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE app.opinion_drafts
                       SET final_content=:final_content,updated_at=:updated_at,updated_by=:updated_by
                     WHERE draft_id=:draft_id
                """),
                {
                    "draft_id": draft["draftId"],
                    "final_content": draft["finalContent"],
                    "updated_at": draft["updatedAt"],
                    "updated_by": draft["updatedBy"],
                },
            )

    @staticmethod
    def _report(row: Any) -> dict[str, Any]:
        snapshot = dict(row["report_payload"])
        encoded = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return {
            "reportId": row["report_id"],
            "reviewId": row["review_id"],
            "sourceReportId": row["source_report_id"],
            "reportType": row["report_type"],
            "format": row["report_format"],
            "reportStatus": row["report_status"],
            "snapshotHash": row["snapshot_hash"],
            "snapshotVersion": row["snapshot_version"],
            "rendererVersion": row["renderer_version"],
            "converterVersion": row["converter_version"],
            "downloadUrl": (
                f"/api/v1/reports/{row['report_id']}/download"
                if row["report_status"] != "FAILED"
                else None
            ),
            "createdAt": _iso(row["created_at"]),
            "_snapshot": snapshot,
            "_bytes": encoded,
        }

    def save_report(self, report: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO app.reports
                    (report_id,review_id,source_report_id,report_type,report_format,report_status,
                     report_payload,snapshot_hash,snapshot_version,renderer_version,converter_version,
                     failure_reason,include_annotations,include_suggestions,include_opinion_draft,
                     include_evidence_details,created_at,created_by)
                    VALUES (:report_id,:review_id,:source_id,:report_type,:format,:status,
                            CAST(:payload AS jsonb),:hash,:snapshot_version,:renderer,:converter,
                            :failure_reason,:annotations,:suggestions,:draft,:evidence,:created_at,:created_by)
                """),
                {
                    "report_id": report["reportId"],
                    "review_id": report["reviewId"],
                    "source_id": report["sourceReportId"],
                    "report_type": report["reportType"],
                    "format": report["format"],
                    "status": report["reportStatus"],
                    "payload": json.dumps(report["_snapshot"], ensure_ascii=False),
                    "hash": report["snapshotHash"],
                    "snapshot_version": report["snapshotVersion"],
                    "renderer": report["rendererVersion"],
                    "converter": report["converterVersion"],
                    "failure_reason": report.get("failureReason"),
                    "annotations": report["_options"]["includeAnnotations"],
                    "suggestions": report["_options"]["includeSuggestions"],
                    "draft": report["_options"]["includeOpinionDraft"],
                    "evidence": report["_options"]["includeEvidenceDetails"],
                    "created_at": report["createdAt"],
                    "created_by": report["createdBy"],
                },
            )

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM app.reports WHERE report_id=:report_id"),
                {"report_id": report_id},
            ).mappings().first()
        return self._report(row) if row else None

    @staticmethod
    def _comparison(row: Any, items: list[Any]) -> dict[str, Any]:
        return {
            "comparisonId": row["comparison_id"],
            "advertisementId": row["advertisement_id"],
            "comparisonStatus": row["comparison_status"],
            "resolvedIssueCount": row["resolved_issue_count"],
            "unresolvedIssueCount": row["unresolved_issue_count"],
            "newIssueCount": row["new_issue_count"],
            "items": [
                {
                    "reviewItemId": item["review_item_id"],
                    "originalText": item["original_text"],
                    "revisedText": item["revised_text"],
                    "resolutionStatus": item["resolution_status"],
                    "comment": item["comment"],
                    "reanalysisReviewId": item["reanalysis_review_id"],
                }
                for item in items
            ],
            "_baseReviewId": row["base_review_id"],
            "_revisionId": row["revision_id"],
        }

    def save_comparison(self, comparison: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO app.comparisons
                    (comparison_id,advertisement_id,base_review_id,revision_id,reanalysis_review_id,
                     comparison_status,compare_types,resolved_issue_count,unresolved_issue_count,
                     new_issue_count,created_at,created_by)
                    VALUES (:comparison_id,:advertisement_id,:base_review_id,:revision_id,
                            :reanalysis_review_id,:status,CAST(:types AS jsonb),:resolved,:unresolved,
                            :new_count,:created_at,:created_by)
                """),
                {
                    "comparison_id": comparison["comparisonId"],
                    "advertisement_id": comparison["advertisementId"],
                    "base_review_id": comparison["_baseReviewId"],
                    "revision_id": comparison["_revisionId"],
                    "reanalysis_review_id": next(
                        (
                            item["reanalysisReviewId"]
                            for item in comparison["items"]
                            if item["reanalysisReviewId"]
                        ),
                        None,
                    ),
                    "status": comparison["comparisonStatus"],
                    "types": json.dumps(comparison["_compareTypes"]),
                    "resolved": comparison["resolvedIssueCount"],
                    "unresolved": comparison["unresolvedIssueCount"],
                    "new_count": comparison["newIssueCount"],
                    "created_at": comparison["_createdAt"],
                    "created_by": comparison["_createdBy"],
                },
            )
            for item in comparison["items"]:
                connection.execute(
                    text("""
                        INSERT INTO app.comparison_items
                        (comparison_item_id,comparison_id,review_item_id,original_text,revised_text,
                         resolution_status,comment,reanalysis_review_id,created_at)
                        VALUES (:item_id,:comparison_id,:review_item_id,:original_text,:revised_text,
                                :status,:comment,:reanalysis_review_id,:created_at)
                    """),
                    {
                        "item_id": str(uuid4()),
                        "comparison_id": comparison["comparisonId"],
                        "review_item_id": item["reviewItemId"],
                        "original_text": item["originalText"],
                        "revised_text": item["revisedText"],
                        "status": item["resolutionStatus"],
                        "comment": item["comment"],
                        "reanalysis_review_id": item["reanalysisReviewId"],
                        "created_at": comparison["_createdAt"],
                    },
                )

    def get_comparison(self, comparison_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM app.comparisons WHERE comparison_id=:comparison_id"),
                {"comparison_id": comparison_id},
            ).mappings().first()
            if row is None:
                return None
            items = connection.execute(
                text(
                    "SELECT * FROM app.comparison_items WHERE comparison_id=:comparison_id "
                    "ORDER BY created_at,comparison_item_id"
                ),
                {"comparison_id": comparison_id},
            ).mappings().all()
        return self._comparison(row, list(items))


class SupportService:
    """Builds governed support outputs and delegates all state to a repository."""

    def __init__(
        self,
        repository: SupportRepository | None = None,
        audit_sink: AuditSink | None = None,
        *,
        reviews: ReviewService | None = None,
        advertisements: AdvertisementService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository or InMemorySupportRepository()
        self._audit_sink = audit_sink
        self._reviews = reviews
        self._advertisements = advertisements
        self._now_value = now or (lambda: datetime.now(UTC))

    @property
    def suggestions(self) -> dict[str, dict[str, Any]]:
        return getattr(self.repository, "suggestions", {})

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return getattr(self.repository, "decisions", [])

    @property
    def questions(self) -> list[dict[str, Any]]:
        return getattr(self.repository, "questions", [])

    @property
    def drafts(self) -> dict[str, dict[str, Any]]:
        return getattr(self.repository, "drafts", {})

    @property
    def reports(self) -> dict[str, dict[str, Any]]:
        return getattr(self.repository, "reports", {})

    @property
    def comparisons(self) -> dict[str, dict[str, Any]]:
        return getattr(self.repository, "comparisons", {})

    def _now(self) -> datetime:
        return self._now_value()

    def _now_text(self) -> str:
        return self._now().isoformat().replace("+00:00", "Z")

    @staticmethod
    def _suggestion_response(suggestion: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(suggestion[key])
            for key in (
                "suggestionId",
                "reviewItemId",
                "originalText",
                "suggestedText",
                "suggestionReason",
                "evidenceIds",
                "decisionStatus",
            )
        }

    @staticmethod
    def _draft_response(draft: dict[str, Any]) -> dict[str, Any]:
        response = {
            key: deepcopy(draft.get(key))
            for key in (
                "draftId",
                "reviewId",
                "draftContent",
                "finalContent",
                "includedReviewItemIds",
                "createdAt",
                "updatedAt",
            )
        }
        response["createdAt"] = _iso(draft.get("createdAt"))
        response["updatedAt"] = _iso(draft.get("updatedAt"))
        return response

    @staticmethod
    def _report_response(report: dict[str, Any]) -> dict[str, Any]:
        response = {
            key: deepcopy(report.get(key))
            for key in (
                "reportId",
                "reviewId",
                "sourceReportId",
                "reportType",
                "format",
                "reportStatus",
                "snapshotHash",
                "snapshotVersion",
                "rendererVersion",
                "converterVersion",
                "downloadUrl",
                "createdAt",
            )
        }
        response["createdAt"] = _iso(report.get("createdAt"))
        return response

    @staticmethod
    def _comparison_response(comparison: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(comparison[key])
            for key in (
                "comparisonId",
                "advertisementId",
                "comparisonStatus",
                "resolvedIssueCount",
                "unresolvedIssueCount",
                "newIssueCount",
                "items",
            )
        }

    def _authorize_review(
        self, actor: CurrentUser, review_id: str, trace_id: str
    ) -> None:
        if self._reviews is not None:
            self._reviews.status(actor, review_id, trace_id)

    def _authorize_advertisement(
        self, actor: CurrentUser, advertisement_id: str, trace_id: str
    ) -> None:
        if self._advertisements is not None:
            self._advertisements.get(actor, advertisement_id, trace_id)

    def list_suggestions(
        self, actor: CurrentUser, review_id: str, trace_id: str = "support-direct"
    ) -> list[dict[str, Any]]:
        self._authorize_review(actor, review_id, trace_id)
        return [
            self._suggestion_response(value)
            for value in self.repository.list_suggestions(review_id)
        ]

    def decide(
        self,
        actor: CurrentUser,
        suggestion_id: str,
        body: dict[str, Any],
        trace_id: str = "support-direct",
    ) -> dict[str, Any]:
        suggestion = self.repository.get_suggestion(suggestion_id)
        if suggestion is None:
            raise ServiceError(404, "NOT_FOUND", "추천 문구를 찾을 수 없습니다.")
        self._authorize_review(actor, suggestion["reviewId"], trace_id)
        status = body.get("decisionStatus")
        final_text = body.get("finalText")
        if status not in {"ACCEPTED", "REJECTED", "MODIFIED_AND_USED"}:
            raise ServiceError(400, "BAD_REQUEST", "판단 상태를 확인해 주세요.")
        if status == "MODIFIED_AND_USED" and (
            not isinstance(final_text, str) or not final_text.strip()
        ):
            raise ServiceError(400, "BAD_REQUEST", "수정 후 사용 문구를 입력해 주세요.")
        resolved = (
            final_text.strip()
            if isinstance(final_text, str)
            else suggestion["suggestedText"]
            if status == "ACCEPTED"
            else None
        )
        now = self._now()
        self.repository.save_decision(
            {
                "suggestionId": suggestion_id,
                "decisionStatus": status,
                "finalText": resolved,
                "comment": body.get("comment"),
                "decidedBy": actor.user_id,
                "decidedAt": now,
            }
        )
        self._audit(actor, "SUGGESTION_DECISION_CREATE", suggestion_id, trace_id)
        return {
            "suggestionId": suggestion_id,
            "decisionStatus": status,
            "finalText": resolved,
            "updatedAt": _iso(now),
        }

    def question(
        self,
        actor: CurrentUser,
        body: dict[str, Any],
        trace_id: str = "support-direct",
    ) -> dict[str, Any]:
        question = body.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ServiceError(400, "BAD_REQUEST", "질문을 입력해 주세요.")
        answer: dict[str, Any] = {
            "qaId": self.repository.next_identifier("QA"),
            "answerSummary": "확인 가능한 근거가 부족할 수 있습니다.",
            "answerDetail": "자동 확정 답변이 아니며 담당자 확인이 필요합니다.",
            "evidences": [],
            "suggestedPhrases": [],
            "needsHumanReview": True,
        }
        self.repository.save_question(
            actor,
            {
                "sessionId": self.repository.next_identifier("QAS"),
                "question": question.strip(),
                "productGroup": body.get("productGroup"),
                "advertisementType": body.get("advertisementType"),
                "standardEffectiveDate": body.get("standardEffectiveDate"),
                "standardVersionIds": [],
                "answer": deepcopy(answer),
                "createdAt": self._now(),
            },
        )
        self._audit(actor, "QA_QUESTION_CREATE", answer["qaId"], trace_id)
        return answer

    def list_questions(self, actor: CurrentUser) -> list[dict[str, Any]]:
        return [
            deepcopy(value.get("answer", value))
            for value in self.repository.list_questions(actor)
        ]

    def drafts_for(
        self, actor: CurrentUser, review_id: str, trace_id: str = "support-direct"
    ) -> list[dict[str, Any]]:
        self._authorize_review(actor, review_id, trace_id)
        return [self._draft_response(value) for value in self.repository.list_drafts(review_id)]

    def create_draft(
        self,
        actor: CurrentUser,
        review_id: str,
        body: dict[str, Any],
        trace_id: str = "support-direct",
    ) -> dict[str, Any]:
        self._authorize_review(actor, review_id, trace_id)
        now = self._now()
        draft = {
            "draftId": self.repository.next_identifier("DRAFT"),
            "reviewId": review_id,
            "templateType": body.get("templateType", "DEFAULT"),
            "draftContent": "담당자 검토가 필요한 심의 의견 초안입니다.",
            "finalContent": None,
            "includedReviewItemIds": deepcopy(body.get("includeReviewItemIds", [])),
            "additionalInstruction": body.get("additionalInstruction"),
            "createdAt": now,
            "createdBy": actor.user_id,
            "updatedAt": None,
        }
        self.repository.save_draft(draft)
        self._audit(actor, "OPINION_DRAFT_CREATE", draft["draftId"], trace_id)
        return self._draft_response({**draft, "createdAt": _iso(now)})

    def update_draft(
        self,
        actor: CurrentUser,
        draft_id: str,
        body: dict[str, Any],
        trace_id: str = "support-direct",
    ) -> dict[str, Any]:
        draft = self.repository.get_draft(draft_id)
        text_value = body.get("finalContent")
        if draft is None:
            raise ServiceError(404, "NOT_FOUND", "의견 초안을 찾을 수 없습니다.")
        self._authorize_review(actor, draft["reviewId"], trace_id)
        if not isinstance(text_value, str) or not text_value.strip():
            raise ServiceError(400, "BAD_REQUEST", "최종 의견을 입력해 주세요.")
        updated_at = self._now()
        draft["finalContent"] = text_value.strip()
        draft["updatedAt"] = updated_at
        draft["updatedBy"] = actor.user_id
        self.repository.update_draft(draft)
        self._audit(actor, "OPINION_DRAFT_UPDATE", draft_id, trace_id)
        return self._draft_response({**draft, "updatedAt": _iso(updated_at)})

    def create_report(
        self,
        actor: CurrentUser,
        review_id: str,
        body: dict[str, Any],
        trace_id: str = "support-direct",
    ) -> dict[str, Any]:
        self._authorize_review(actor, review_id, trace_id)
        requested_format = body.get("format", "HWPX")
        if requested_format not in {"HWPX", "PDF"}:
            raise ServiceError(400, "BAD_REQUEST", "지원하지 않는 보고서 형식입니다.")
        snapshot = {
            "reviewId": review_id,
            "suggestions": [
                self._suggestion_response(value)
                for value in self.repository.list_suggestions(review_id)
            ],
            "drafts": [
                self._draft_response(value) for value in self.repository.list_drafts(review_id)
            ],
            "options": {
                key: body.get(key, False)
                for key in (
                    "includeAnnotations",
                    "includeSuggestions",
                    "includeOpinionDraft",
                    "includeEvidenceDetails",
                )
            },
        }
        encoded_snapshot = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        snapshot_hash = f"sha256:{hashlib.sha256(encoded_snapshot).hexdigest()}"
        source_report_id = None
        if requested_format == "PDF":
            source_report_id = self._save_report(
                actor, review_id, body, "HWPX", None, snapshot, encoded_snapshot, snapshot_hash
            )["reportId"]
        report = self._save_report(
            actor,
            review_id,
            body,
            requested_format,
            source_report_id,
            snapshot,
            encoded_snapshot,
            snapshot_hash,
        )
        self._audit(actor, "REPORT_CREATE", report["reportId"], trace_id)
        return self._report_response(report)

    def _save_report(
        self,
        actor: CurrentUser,
        review_id: str,
        body: dict[str, Any],
        report_format: str,
        source_report_id: str | None,
        snapshot: dict[str, Any],
        encoded_snapshot: bytes,
        snapshot_hash: str,
    ) -> dict[str, Any]:
        report_id = self.repository.next_identifier("RPT")
        options = {
            key: bool(body.get(key, False))
            for key in (
                "includeAnnotations",
                "includeSuggestions",
                "includeOpinionDraft",
                "includeEvidenceDetails",
            )
        }
        report = {
            "reportId": report_id,
            "reviewId": review_id,
            "sourceReportId": source_report_id,
            "reportType": body.get("reportType", "FULL"),
            "format": report_format,
            "reportStatus": "CREATED",
            "snapshotHash": snapshot_hash,
            "snapshotVersion": "report-snapshot-v1",
            "rendererVersion": "deterministic-hwpx-v1",
            "converterVersion": "deterministic-pdf-v1" if report_format == "PDF" else None,
            "downloadUrl": f"/api/v1/reports/{report_id}/download",
            "createdAt": self._now(),
            "createdBy": actor.user_id,
            "_snapshot": deepcopy(snapshot),
            "_bytes": bytes(encoded_snapshot),
            "_options": options,
        }
        if report_format == "PDF" and body.get("forceConversionFailure"):
            report["reportStatus"] = "FAILED"
            report["downloadUrl"] = None
            report["converterVersion"] = "deterministic-pdf-v1:failed"
            report["failureReason"] = "forced deterministic conversion failure"
        self.repository.save_report(report)
        return report

    def get_report(
        self, actor: CurrentUser, report_id: str, trace_id: str = "support-direct"
    ) -> dict[str, Any]:
        report = self.repository.get_report(report_id)
        if report is None:
            raise ServiceError(404, "NOT_FOUND", "보고서를 찾을 수 없습니다.")
        self._authorize_review(actor, report["reviewId"], trace_id)
        return self._report_response(report)

    def download_report(
        self,
        actor: CurrentUser,
        report_id: str,
        trace_id: str = "support-direct",
    ) -> tuple[bytes, str]:
        if not set(actor.roles).intersection({"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}):
            raise ServiceError(403, "FORBIDDEN", "보고서 다운로드 권한이 없습니다.")
        report = self.repository.get_report(report_id)
        if report is None:
            raise ServiceError(404, "NOT_FOUND", "보고서를 찾을 수 없습니다.")
        self._authorize_review(actor, report["reviewId"], trace_id)
        if report["reportStatus"] == "FAILED":
            raise ServiceError(409, "CONFLICT", "변환에 실패한 보고서는 다운로드할 수 없습니다.")
        self._audit(actor, "REPORT_DOWNLOADED", report_id, trace_id)
        return bytes(report["_bytes"]), report["format"]

    def create_comparison(
        self,
        actor: CurrentUser,
        advertisement_id: str,
        body: dict[str, Any],
        trace_id: str = "support-direct",
    ) -> dict[str, Any]:
        self._authorize_advertisement(actor, advertisement_id, trace_id)
        if not body.get("revisionId") or not body.get("baseReviewId"):
            raise ServiceError(400, "BAD_REQUEST", "기준 검토와 수정본이 필요합니다.")
        if self._advertisements is not None:
            revision = self._advertisements.repository.get_revision(body["revisionId"])
            if revision is None:
                raise ServiceError(404, "NOT_FOUND", "수정본을 찾을 수 없습니다.")
            if revision.advertisement_id != advertisement_id:
                raise ServiceError(400, "BAD_REQUEST", "광고물에 속한 수정본을 선택해 주세요.")
        if self._reviews is not None:
            base = self._reviews.status(actor, body["baseReviewId"], trace_id)
            if base.review.advertisement_id != advertisement_id:
                raise ServiceError(400, "BAD_REQUEST", "광고물에 속한 기준 검토를 선택해 주세요.")
        items = [
            {
                "reviewItemId": None,
                "originalText": "기존 지적 사항",
                "revisedText": "수정 완료 문구",
                "resolutionStatus": "RESOLVED",
                "comment": "수정 사항이 반영되었습니다.",
                "reanalysisReviewId": None,
            },
            {
                "reviewItemId": None,
                "originalText": "근거가 불명확한 표현",
                "revisedText": "근거가 불명확한 표현",
                "resolutionStatus": "UNRESOLVED",
                "comment": "추가 수정이 필요합니다.",
                "reanalysisReviewId": body["baseReviewId"],
            },
            {
                "reviewItemId": None,
                "originalText": None,
                "revisedText": "새로운 표현",
                "resolutionStatus": "NEW_ISSUE",
                "comment": "수정본에서 새 위험이 발견되었습니다.",
                "reanalysisReviewId": body["baseReviewId"],
            },
        ]
        result = {
            "comparisonId": self.repository.next_identifier("CMP"),
            "advertisementId": advertisement_id,
            "comparisonStatus": "COMPLETED",
            "resolvedIssueCount": 1,
            "unresolvedIssueCount": 1,
            "newIssueCount": 1,
            "items": items,
            "_baseReviewId": body["baseReviewId"],
            "_revisionId": body["revisionId"],
            "_compareTypes": body.get("compareTypes", []),
            "_createdAt": self._now(),
            "_createdBy": actor.user_id,
        }
        self.repository.save_comparison(result)
        self._audit(actor, "COMPARISON_CREATE", result["comparisonId"], trace_id)
        return self._comparison_response(result)

    def get_comparison(
        self, actor: CurrentUser, comparison_id: str, trace_id: str = "support-direct"
    ) -> dict[str, Any]:
        comparison = self.repository.get_comparison(comparison_id)
        if comparison is None:
            raise ServiceError(404, "NOT_FOUND", "비교 결과를 찾을 수 없습니다.")
        self._authorize_advertisement(actor, comparison["advertisementId"], trace_id)
        return self._comparison_response(comparison)

    def _audit(
        self,
        actor: CurrentUser,
        action: str,
        target_id: str,
        trace_id: str,
    ) -> None:
        if self._audit_sink is None:
            return
        self._audit_sink(
            AuditEvent(
                action_type=action,
                result="SUCCESS",
                reason_code=None,
                actor_user_id=actor.user_id,
                actor_department_id=actor.department_id,
                actor_role=actor.roles[0] if actor.roles else None,
                target_type=action.rsplit("_", 1)[0],
                target_id=target_id,
                trace_id=trace_id,
                created_at=self._now(),
            )
        )
