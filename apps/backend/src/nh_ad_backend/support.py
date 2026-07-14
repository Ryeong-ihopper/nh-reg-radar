"""Deterministic, provider-independent M6 reviewer-support behavior."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from nh_ad_backend.domain import AuditEvent, CurrentUser
from nh_ad_backend.services import ServiceError


AuditSink = Callable[[AuditEvent], None]


class SupportService:
    """Keeps governed support outputs deterministic for local and test use.

    The service deliberately stores private provenance (history and report
    snapshots) separately from the OpenAPI response payloads.
    """

    def __init__(self, audit_sink: AuditSink | None = None) -> None:
        self._audit_sink = audit_sink
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

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

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
        return {
            key: deepcopy(draft[key])
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

    @staticmethod
    def _report_response(report: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(report[key])
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

    def list_suggestions(self, _actor: CurrentUser, review_id: str) -> list[dict[str, Any]]:
        return [
            self._suggestion_response(value)
            for value in self.suggestions.values()
            if value["reviewId"] == review_id
        ]

    def decide(
        self, actor: CurrentUser, suggestion_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        suggestion = self.suggestions.get(suggestion_id)
        if suggestion is None:
            raise ServiceError(404, "NOT_FOUND", "추천 문구를 찾을 수 없습니다.")
        status = body.get("decisionStatus")
        final_text = body.get("finalText")
        if status not in {"ACCEPTED", "REJECTED", "MODIFIED_AND_USED"}:
            raise ServiceError(400, "BAD_REQUEST", "판단 상태를 확인해 주세요.")
        if status == "MODIFIED_AND_USED" and (
            not isinstance(final_text, str) or not final_text.strip()
        ):
            raise ServiceError(400, "BAD_REQUEST", "수정 후 사용 문구를 입력해 주세요.")
        resolved = (
            final_text
            if isinstance(final_text, str)
            else suggestion["suggestedText"]
            if status == "ACCEPTED"
            else None
        )
        now = self._now()
        suggestion["decisionStatus"] = status
        self.decisions.append(
            {
                "suggestionId": suggestion_id,
                "decisionStatus": status,
                "finalText": resolved,
                "comment": body.get("comment"),
                "decidedBy": actor.user_id,
                "decidedAt": now,
            }
        )
        return {
            "suggestionId": suggestion_id,
            "decisionStatus": status,
            "finalText": resolved,
            "updatedAt": now,
        }

    def question(self, _actor: CurrentUser, body: dict[str, Any]) -> dict[str, Any]:
        question = body.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ServiceError(400, "BAD_REQUEST", "질문을 입력해 주세요.")
        answer = {
            "qaId": f"QA-{len(self.questions) + 1:04d}",
            "answerSummary": "확인 가능한 근거가 부족할 수 있습니다.",
            "answerDetail": "자동 확정 답변이 아니며 담당자 확인이 필요합니다.",
            "evidences": [],
            "suggestedPhrases": [],
            "needsHumanReview": True,
        }
        self.questions.append(
            {
                "question": question,
                "productGroup": body.get("productGroup"),
                "advertisementType": body.get("advertisementType"),
                "standardEffectiveDate": body.get("standardEffectiveDate"),
                "standardVersionIds": [],
                "answer": deepcopy(answer),
                "createdAt": self._now(),
            }
        )
        return answer

    def list_questions(self, _actor: CurrentUser) -> list[dict[str, Any]]:
        return [deepcopy(question["answer"]) for question in self.questions]

    def drafts_for(self, review_id: str) -> list[dict[str, Any]]:
        return [
            self._draft_response(draft)
            for draft in self.drafts.values()
            if draft["reviewId"] == review_id
        ]

    def create_draft(self, review_id: str, body: dict[str, Any]) -> dict[str, Any]:
        draft_id = f"DRAFT-{len(self.drafts) + 1:04d}"
        draft_content = "담당자 검토가 필요한 심의 의견 초안입니다."
        draft = {
            "draftId": draft_id,
            "reviewId": review_id,
            "draftContent": draft_content,
            "finalContent": None,
            "includedReviewItemIds": deepcopy(body.get("includeReviewItemIds", [])),
            "createdAt": self._now(),
            "updatedAt": None,
            "editHistory": [
                {"content": draft_content, "editedAt": self._now(), "kind": "ORIGINAL"}
            ],
        }
        self.drafts[draft_id] = draft
        return self._draft_response(draft)

    def update_draft(self, draft_id: str, body: dict[str, Any]) -> dict[str, Any]:
        draft = self.drafts.get(draft_id)
        text = body.get("finalContent")
        if draft is None:
            raise ServiceError(404, "NOT_FOUND", "의견 초안을 찾을 수 없습니다.")
        if not isinstance(text, str) or not text.strip():
            raise ServiceError(400, "BAD_REQUEST", "최종 의견을 입력해 주세요.")
        updated_at = self._now()
        draft["finalContent"] = text
        draft["updatedAt"] = updated_at
        draft["editHistory"].append({"content": text, "editedAt": updated_at, "kind": "FINAL"})
        return self._draft_response(draft)

    def create_report(self, review_id: str, body: dict[str, Any]) -> dict[str, Any]:
        requested_format = body.get("format", "HWPX")
        if requested_format not in {"HWPX", "PDF"}:
            raise ServiceError(400, "BAD_REQUEST", "지원하지 않는 보고서 형식입니다.")
        snapshot = {
            "reviewId": review_id,
            "suggestions": self.list_suggestions_for_snapshot(review_id),
            "drafts": [self._draft_response(draft) for draft in self.drafts_for_record(review_id)],
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
                review_id, body, "HWPX", None, snapshot, encoded_snapshot, snapshot_hash
            )["reportId"]
        report = self._save_report(
            review_id,
            body,
            requested_format,
            source_report_id,
            snapshot,
            encoded_snapshot,
            snapshot_hash,
        )
        if requested_format == "PDF" and body.get("forceConversionFailure"):
            report["reportStatus"] = "FAILED"
            report["downloadUrl"] = None
            report["converterVersion"] = "deterministic-pdf-v1:failed"
        return self._report_response(report)

    def _save_report(
        self,
        review_id: str,
        body: dict[str, Any],
        report_format: str,
        source_report_id: str | None,
        snapshot: dict[str, Any],
        encoded_snapshot: bytes,
        snapshot_hash: str,
    ) -> dict[str, Any]:
        report_id = f"RPT-{len(self.reports) + 1:04d}"
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
            "_snapshot": deepcopy(snapshot),
            "_bytes": bytes(encoded_snapshot),
        }
        self.reports[report_id] = report
        return report

    def get_report(self, report_id: str) -> dict[str, Any]:
        report = self.reports.get(report_id)
        if report is None:
            raise ServiceError(404, "NOT_FOUND", "보고서를 찾을 수 없습니다.")
        return self._report_response(report)

    def download_report(self, actor: CurrentUser, report_id: str) -> tuple[bytes, str]:
        if not set(actor.roles).intersection({"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}):
            raise ServiceError(403, "FORBIDDEN", "보고서 다운로드 권한이 없습니다.")
        report = self.reports.get(report_id)
        if report is None:
            raise ServiceError(404, "NOT_FOUND", "보고서를 찾을 수 없습니다.")
        if report["reportStatus"] == "FAILED":
            raise ServiceError(409, "CONFLICT", "변환에 실패한 보고서는 다운로드할 수 없습니다.")
        self._audit_download(actor, report_id)
        return bytes(report["_bytes"]), report["format"]

    def _audit_download(self, actor: CurrentUser, report_id: str) -> None:
        if self._audit_sink is None:
            return
        self._audit_sink(
            AuditEvent(
                action_type="REPORT_DOWNLOADED",
                result="SUCCESS",
                reason_code=None,
                actor_user_id=actor.user_id,
                actor_department_id=actor.department_id,
                actor_role=actor.roles[0] if actor.roles else None,
                target_type="REPORT",
                target_id=report_id,
                trace_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
        )

    def create_comparison(self, advertisement_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if not body.get("revisionId") or not body.get("baseReviewId"):
            raise ServiceError(400, "BAD_REQUEST", "기준 검토와 수정본이 필요합니다.")
        comparison_id = f"CMP-{len(self.comparisons) + 1:04d}"
        items = [
            {
                "reviewItemId": "ITEM-RESOLVED",
                "originalText": "기존 지적 사항",
                "revisedText": "수정 완료 문구",
                "resolutionStatus": "RESOLVED",
                "comment": "수정 사항이 반영되었습니다.",
                "reanalysisReviewId": None,
            },
            {
                "reviewItemId": "ITEM-UNRESOLVED",
                "originalText": "근거가 불명확한 표현",
                "revisedText": "근거가 불명확한 표현",
                "resolutionStatus": "UNRESOLVED",
                "comment": "추가 수정이 필요합니다.",
                "reanalysisReviewId": "REV-REANALYSIS-0001",
            },
            {
                "reviewItemId": "ITEM-NEW",
                "originalText": None,
                "revisedText": "새로운 표현",
                "resolutionStatus": "NEW_ISSUE",
                "comment": "수정본에서 새 위험이 발견되었습니다.",
                "reanalysisReviewId": "REV-REANALYSIS-0001",
            },
        ]
        result = {
            "comparisonId": comparison_id,
            "advertisementId": advertisement_id,
            "comparisonStatus": "COMPLETED",
            "resolvedIssueCount": 1,
            "unresolvedIssueCount": 1,
            "newIssueCount": 1,
            "items": items,
        }
        self.comparisons[comparison_id] = result
        return deepcopy(result)

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        comparison = self.comparisons.get(comparison_id)
        if comparison is None:
            raise ServiceError(404, "NOT_FOUND", "비교 결과를 찾을 수 없습니다.")
        return deepcopy(comparison)

    def list_suggestions_for_snapshot(self, review_id: str) -> list[dict[str, Any]]:
        return self.list_suggestions(
            CurrentUser("snapshot", "snapshot", "system", "system", (), 0), review_id
        )

    def drafts_for_record(self, review_id: str) -> list[dict[str, Any]]:
        return [draft for draft in self.drafts.values() if draft["reviewId"] == review_id]
