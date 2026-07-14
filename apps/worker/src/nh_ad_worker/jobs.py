"""M4 parser/OCR job execution with idempotent state transitions."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from nh_ad_parser_contracts import (
    ArtifactMetadata,
    ArtifactStore,
    DocumentInput,
    NormalizedDocument,
    ParserRouter,
)

if TYPE_CHECKING:
    from nh_ad_worker.results import ReviewResultBundle, ReviewResultEngine


RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=3), timedelta(minutes=10))
MESSAGE_FIELDS = frozenset(
    {"messageVersion", "jobId", "reviewId", "jobType", "correlationId", "idempotencyKey"}
)


class TransientParserError(RuntimeError):
    """Retryable provider, storage, or timeout failure."""


class PermanentParserError(RuntimeError):
    """Corrupt, encrypted, unsupported, or otherwise non-retryable input."""


@dataclass(frozen=True)
class QueueMessage:
    job_id: str
    review_id: str
    job_type: str
    correlation_id: str
    idempotency_key: str
    message_version: str = "review-job-v1"

    @classmethod
    def parse(cls, payload: dict[str, object]) -> "QueueMessage":
        if set(payload) != MESSAGE_FIELDS or payload.get("messageVersion") != "review-job-v1":
            raise ValueError("INVALID_REVIEW_QUEUE_MESSAGE")
        if payload.get("jobType") not in {"REVIEW_ANALYSIS", "RE_REVIEW"}:
            raise ValueError("INVALID_REVIEW_QUEUE_MESSAGE")
        if not all(isinstance(payload.get(key), str) and payload[key] for key in MESSAGE_FIELDS):
            raise ValueError("INVALID_REVIEW_QUEUE_MESSAGE")
        return cls(
            job_id=str(payload["jobId"]),
            review_id=str(payload["reviewId"]),
            job_type=str(payload["jobType"]),
            correlation_id=str(payload["correlationId"]),
            idempotency_key=str(payload["idempotencyKey"]),
        )


@dataclass
class WorkerJob:
    job_id: str
    review_id: str
    document: DocumentInput
    review_step_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "PENDING"
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None
    heartbeat_at: datetime | None = None
    locked_by: str | None = None
    failed_reason_code: str | None = None
    dead_lettered_at: datetime | None = None
    selected_artifact: ArtifactMetadata | None = None
    normalized_document: NormalizedDocument | None = None
    review_results: ReviewResultBundle | None = None
    review_status: str = "ANALYSIS_REQUESTED"


class JobRepository(Protocol):
    def claim(
        self, message: QueueMessage, *, worker_id: str, now: datetime
    ) -> WorkerJob | None: ...
    def heartbeat(self, job_id: str, *, worker_id: str, now: datetime) -> None: ...
    def persist_selected(
        self, job_id: str, document: NormalizedDocument, artifact: ArtifactMetadata
    ) -> None: ...
    def persist_results(self, job_id: str, results: ReviewResultBundle) -> None: ...
    def complete(self, job_id: str, *, now: datetime, check_required: bool) -> None: ...
    def retry_or_dead_letter(self, job_id: str, *, now: datetime, reason_code: str) -> bool: ...
    def fail_final(self, job_id: str, *, now: datetime, reason_code: str) -> None: ...
    def recover_stale(self, *, now: datetime, stale_before: datetime) -> list[QueueMessage]: ...


class InMemoryJobRepository:
    def __init__(self, jobs: Iterable[WorkerJob] = ()) -> None:
        self.jobs = {job.job_id: job for job in jobs}

    def claim(self, message: QueueMessage, *, worker_id: str, now: datetime) -> WorkerJob | None:
        job = self.jobs.get(message.job_id)
        if job is None or job.review_id != message.review_id:
            raise KeyError(message.job_id)
        if message.idempotency_key != job.job_id:
            raise ValueError("IDEMPOTENCY_KEY_MISMATCH")
        if job.status not in {"PENDING", "RETRY_PENDING", "STALE"}:
            return None
        if job.next_retry_at is not None and job.next_retry_at > now:
            return None
        job.status = "RUNNING"
        job.review_status = "ANALYZING"
        job.locked_by = worker_id
        job.heartbeat_at = now
        return job

    def heartbeat(self, job_id: str, *, worker_id: str, now: datetime) -> None:
        job = self.jobs[job_id]
        if job.status != "RUNNING" or job.locked_by != worker_id:
            raise ValueError("ILLEGAL_JOB_TRANSITION")
        job.heartbeat_at = now

    def persist_selected(
        self, job_id: str, document: NormalizedDocument, artifact: ArtifactMetadata
    ) -> None:
        if not artifact.is_selected_output:
            raise ValueError("UNSELECTED_OUTPUT_PERSISTENCE_FORBIDDEN")
        job = self.jobs[job_id]
        if job.selected_artifact is not None:
            raise ValueError("SELECTED_OUTPUT_ALREADY_PERSISTED")
        job.selected_artifact = artifact
        job.normalized_document = document

    def persist_results(self, job_id: str, results: ReviewResultBundle) -> None:
        job = self.jobs[job_id]
        if job.normalized_document is None or results.review_id != job.review_id:
            raise ValueError("REVIEW_RESULT_SOURCE_NOT_PERSISTED")
        if job.review_results is not None:
            raise ValueError("REVIEW_RESULTS_ALREADY_PERSISTED")
        job.review_results = results

    def complete(self, job_id: str, *, now: datetime, check_required: bool) -> None:
        job = self.jobs[job_id]
        if job.status != "RUNNING" or job.normalized_document is None:
            raise ValueError("ILLEGAL_JOB_TRANSITION")
        job.status = "COMPLETED"
        job.review_status = "CHECK_REQUIRED" if check_required else "REVIEW_COMPLETED"
        job.heartbeat_at = now

    def retry_or_dead_letter(self, job_id: str, *, now: datetime, reason_code: str) -> bool:
        job = self.jobs[job_id]
        if job.status != "RUNNING":
            raise ValueError("ILLEGAL_JOB_TRANSITION")
        job.failed_reason_code = reason_code
        job.locked_by = None
        if job.retry_count >= job.max_retries:
            job.status = "FAILED_FINAL"
            job.review_status = "REVIEW_FAILED"
            job.dead_lettered_at = now
            return False
        job.retry_count += 1
        job.status = "RETRY_PENDING"
        job.next_retry_at = now + RETRY_DELAYS[job.retry_count - 1]
        return True

    def fail_final(self, job_id: str, *, now: datetime, reason_code: str) -> None:
        job = self.jobs[job_id]
        if job.status != "RUNNING":
            raise ValueError("ILLEGAL_JOB_TRANSITION")
        job.status = "FAILED_FINAL"
        job.review_status = "REVIEW_FAILED"
        job.failed_reason_code = reason_code
        job.locked_by = None
        job.dead_lettered_at = now

    def recover_stale(self, *, now: datetime, stale_before: datetime) -> list[QueueMessage]:
        recovered: list[QueueMessage] = []
        for job in self.jobs.values():
            if (
                job.status != "RUNNING"
                or job.heartbeat_at is None
                or job.heartbeat_at > stale_before
            ):
                continue
            job.status = "STALE"
            job.locked_by = None
            recovered.append(
                QueueMessage(
                    job_id=job.job_id,
                    review_id=job.review_id,
                    job_type="REVIEW_ANALYSIS",
                    correlation_id=f"recovery-{job.job_id}",
                    idempotency_key=job.job_id,
                )
            )
        return recovered


class DeadLetterSink(Protocol):
    def publish(self, payload: dict[str, str]) -> None: ...


class InMemoryDeadLetterSink:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def publish(self, payload: dict[str, str]) -> None:
        self.messages.append(payload)


class ParserJobProcessor:
    def __init__(
        self,
        repository: JobRepository,
        router: ParserRouter,
        artifacts: ArtifactStore,
        dead_letters: DeadLetterSink,
        *,
        worker_id: str,
        now: Callable[[], datetime] | None = None,
        raw_output: Callable[[DocumentInput, NormalizedDocument], bytes] | None = None,
        result_engine: ReviewResultEngine | None = None,
    ) -> None:
        self.repository = repository
        self.router = router
        self.artifacts = artifacts
        self.dead_letters = dead_letters
        self.worker_id = worker_id
        self._now = now or (lambda: datetime.now(UTC))
        self._raw_output = raw_output or (
            lambda _input, output: output.model_dump_json(by_alias=True).encode("utf-8")
        )
        self._result_engine = result_engine

    def process(self, payload: dict[str, object]) -> str:
        message = QueueMessage.parse(payload)
        now = self._now()
        job = self.repository.claim(message, worker_id=self.worker_id, now=now)
        if job is None:
            return "DUPLICATE_IGNORED"
        try:
            selection = self.router.parse_with_attempts(job.document)
            selected_artifact: ArtifactMetadata | None = None
            for attempt in selection.attempts:
                normalized = attempt.normalized_document
                raw = self._raw_output(job.document, normalized)
                artifact = self.artifacts.put(
                    raw,
                    raw_artifact_id=f"ART-{uuid4()}",
                    review_id=job.review_id,
                    file_id=job.document.source_file_id,
                    review_step_id=job.review_step_id,
                    artifact_type="PROVIDER_RAW",
                    content_type="application/json",
                    parser_name=attempt.adapter_name,
                    parser_version=normalized.parser_version,
                    parser_rule_version=normalized.parser_rule_version,
                    ir_version=normalized.ir_version,
                    attempt_no=attempt.attempt_no,
                    is_primary_attempt=attempt.is_primary_attempt,
                    is_selected_output=attempt.is_selected_output,
                    rerun_reason_code=attempt.rerun_reason_code,
                    confidence_score=normalized.confidence.score,
                    confidence_status=normalized.confidence.status.value,
                    created_at=now,
                    retention_until=now + timedelta(days=14),
                )
                if attempt.is_selected_output:
                    selected_artifact = artifact
            if selected_artifact is None:
                raise ValueError("PARSER_SELECTION_REQUIRES_EXACTLY_ONE_OUTPUT")
            normalized = selection.selected_document
            self.repository.persist_selected(job.job_id, normalized, selected_artifact)
            check_required = normalized.confidence.status.value != "READABLE"
            if self._result_engine is not None:
                results = self._result_engine.execute(normalized)
                self.repository.persist_results(job.job_id, results)
                check_required = check_required or results.check_required
            self.repository.complete(job.job_id, now=now, check_required=check_required)
            return "CHECK_REQUIRED" if check_required else "COMPLETED"
        except TransientParserError as exc:
            retrying = self.repository.retry_or_dead_letter(
                job.job_id, now=now, reason_code=type(exc).__name__.upper()
            )
            if not retrying:
                self.dead_letters.publish(
                    {
                        "messageVersion": message.message_version,
                        "jobId": message.job_id,
                        "reviewId": message.review_id,
                        "reasonCode": type(exc).__name__.upper(),
                    }
                )
            return "RETRY_PENDING" if retrying else "FAILED_FINAL"
        except PermanentParserError as exc:
            self.repository.fail_final(job.job_id, now=now, reason_code=type(exc).__name__.upper())
            self.dead_letters.publish(
                {
                    "messageVersion": message.message_version,
                    "jobId": message.job_id,
                    "reviewId": message.review_id,
                    "reasonCode": type(exc).__name__.upper(),
                }
            )
            return "FAILED_FINAL"


def redacted_log(payload: dict[str, object]) -> str:
    """Log only the queue envelope fields and never raw provider content."""
    message = QueueMessage.parse(payload)
    return json.dumps(
        {
            "messageVersion": message.message_version,
            "jobId": message.job_id,
            "reviewId": message.review_id,
            "jobType": message.job_type,
            "correlationId": message.correlation_id,
        },
        separators=(",", ":"),
    )
