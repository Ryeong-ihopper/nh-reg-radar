"""M4 asynchronous review/job application boundary.

PostgreSQL is the status source of truth.  Redis messages deliberately carry
only stable identifiers needed to wake a worker; document and provider data
remain behind repository and object-storage boundaries.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.services import AdvertisementService, ServiceError


ACTIVE_REVIEW_STATUSES = frozenset({"ANALYSIS_REQUESTED", "ANALYZING"})
ACTIVE_JOB_STATUSES = frozenset({"PENDING", "RUNNING", "RETRY_PENDING", "STALE"})
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=3), timedelta(minutes=10))
DEFAULT_REVIEW_TYPES = (
    "REQUIRED_PHRASE",
    "INTEREST_RATE",
    "MISLEADING_EXPRESSION",
    "PRODUCT_CONSISTENCY",
    "VISIBILITY",
    "OCR_QUALITY",
)
STEP_DEFINITIONS = (
    ("FILE_PREPROCESSING", "파일 전처리", 300),
    ("OCR_EXTRACTION", "OCR/VLM 텍스트 추출", 600),
    ("LAYOUT_ANALYSIS", "레이아웃 분석", 300),
    ("RULE_REVIEW", "Rule Engine 검토", 300),
    ("RAG_REVIEW", "RAG Engine 검토", 600),
    ("RESULT_GENERATION", "결과 생성", 300),
)


@dataclass(frozen=True)
class ReviewQueueMessage:
    job_id: str
    review_id: str
    job_type: str
    correlation_id: str
    idempotency_key: str
    message_version: str = "review-job-v1"

    def as_dict(self) -> dict[str, str]:
        return {
            "messageVersion": self.message_version,
            "jobId": self.job_id,
            "reviewId": self.review_id,
            "jobType": self.job_type,
            "correlationId": self.correlation_id,
            "idempotencyKey": self.idempotency_key,
        }


class ReviewQueue(Protocol):
    def publish(self, message: ReviewQueueMessage) -> None: ...


class InMemoryReviewQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def publish(self, message: ReviewQueueMessage) -> None:
        self.messages.append(message.as_dict())


class RedisReviewQueue:
    """Redis list delivery with a frozen, minimal JSON payload."""

    def __init__(self, redis_url: str, queue_name: str = "review-jobs-v1") -> None:
        from redis import Redis

        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._queue_name = queue_name

    def publish(self, message: ReviewQueueMessage) -> None:
        self._client.rpush(
            self._queue_name,
            json.dumps(message.as_dict(), ensure_ascii=False, separators=(",", ":")),
        )


@dataclass
class ReviewStep:
    review_step_id: UUID
    step_code: str
    step_name: str
    status: str
    sequence_no: int
    timeout_at: datetime | None
    failed_reason_code: str | None = None


@dataclass
class ReviewJob:
    job_id: str
    review_id: str
    job_type: str
    status: str
    progress_rate: float
    retry_count: int
    max_retries: int
    timeout_at: datetime
    current_step: str | None = None
    next_retry_at: datetime | None = None
    failed_reason_code: str | None = None
    failed_reason: str | None = None
    is_retryable: bool = True
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Review:
    review_id: str
    advertisement_id: str
    parent_review_id: str | None
    review_round: int
    status: str
    standard_effective_date: date
    standard_version_ids: tuple[str, ...]
    review_types: tuple[str, ...]
    include_suggestion: bool
    include_opinion_draft: bool
    request_memo: str | None
    requested_at: datetime
    requested_by: str
    completed_at: datetime | None = None
    overall_risk_level: str | None = None


@dataclass
class ReviewBundle:
    review: Review
    job: ReviewJob
    steps: list[ReviewStep]


class ReviewRepository(Protocol):
    def active_review_id(self, advertisement_id: str) -> str | None: ...
    def next_round(self, advertisement_id: str) -> int: ...
    def add(self, bundle: ReviewBundle) -> None: ...
    def get(self, review_id: str) -> ReviewBundle | None: ...
    def list(self, advertisement_id: str) -> list[Review]: ...


class InMemoryReviewRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._items: dict[str, ReviewBundle] = {}

    def active_review_id(self, advertisement_id: str) -> str | None:
        with self._lock:
            return next(
                (
                    item.review.review_id
                    for item in self._items.values()
                    if item.review.advertisement_id == advertisement_id
                    and item.job.status in ACTIVE_JOB_STATUSES
                ),
                None,
            )

    def next_round(self, advertisement_id: str) -> int:
        with self._lock:
            rounds = [
                item.review.review_round
                for item in self._items.values()
                if item.review.advertisement_id == advertisement_id
            ]
        return max(rounds, default=0) + 1

    def add(self, bundle: ReviewBundle) -> None:
        with self._lock:
            if self.active_review_id(bundle.review.advertisement_id):
                raise ValueError("REVIEW_ALREADY_RUNNING")
            self._items[bundle.review.review_id] = bundle

    def get(self, review_id: str) -> ReviewBundle | None:
        with self._lock:
            return self._items.get(review_id)

    def list(self, advertisement_id: str) -> list[Review]:
        with self._lock:
            values = [
                item.review
                for item in self._items.values()
                if item.review.advertisement_id == advertisement_id
            ]
        return sorted(values, key=lambda item: item.review_round, reverse=True)


class PostgresReviewRepository:
    """SQL implementation over migration 0004 without a second ORM model."""

    def __init__(self, engine: Engine, queue_name: str = "review-jobs-v1") -> None:
        self._engine = engine
        self._queue_name = queue_name

    def active_review_id(self, advertisement_id: str) -> str | None:
        with self._engine.connect() as connection:
            return connection.execute(
                text("""
                    SELECT r.review_id
                      FROM app.reviews r JOIN app.review_jobs j USING (review_id)
                     WHERE r.advertisement_id=:advertisement_id
                       AND j.job_status IN ('PENDING','RUNNING','RETRY_PENDING','STALE')
                     LIMIT 1
                """),
                {"advertisement_id": advertisement_id},
            ).scalar_one_or_none()

    def next_round(self, advertisement_id: str) -> int:
        with self._engine.connect() as connection:
            value = connection.execute(
                text(
                    "SELECT COALESCE(MAX(review_round),0)+1 FROM app.reviews WHERE advertisement_id=:id"
                ),
                {"id": advertisement_id},
            ).scalar_one()
        return int(value)

    def add(self, bundle: ReviewBundle) -> None:
        review, job = bundle.review, bundle.job
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO app.reviews
                        (review_id,advertisement_id,parent_review_id,review_round,review_status,
                         standard_effective_date,applied_standard_version_ids,review_types,
                         include_suggestion,include_opinion_draft,request_memo,requested_at,
                         requested_by,created_at,updated_at)
                        VALUES (:review_id,:advertisement_id,:parent_review_id,:review_round,:status,
                         :effective_date,CAST(:versions AS jsonb),CAST(:types AS jsonb),:suggestion,
                         :opinion,:memo,:requested_at,:requested_by,:requested_at,:requested_at)
                    """),
                    {
                        "review_id": review.review_id,
                        "advertisement_id": review.advertisement_id,
                        "parent_review_id": review.parent_review_id,
                        "review_round": review.review_round,
                        "status": review.status,
                        "effective_date": review.standard_effective_date,
                        "versions": json.dumps(review.standard_version_ids),
                        "types": json.dumps(review.review_types),
                        "suggestion": review.include_suggestion,
                        "opinion": review.include_opinion_draft,
                        "memo": review.request_memo,
                        "requested_at": review.requested_at,
                        "requested_by": review.requested_by,
                    },
                )
                connection.execute(
                    text("""
                        INSERT INTO app.review_jobs
                        (job_id,review_id,job_type,job_status,queue_name,progress_rate,retry_count,
                         max_retries,timeout_at,is_retryable,created_at)
                        VALUES (:job_id,:review_id,:job_type,:status,:queue,0,0,3,:timeout,true,:created)
                    """),
                    {
                        "job_id": job.job_id,
                        "review_id": job.review_id,
                        "job_type": job.job_type,
                        "status": job.status,
                        "queue": self._queue_name,
                        "timeout": job.timeout_at,
                        "created": review.requested_at,
                    },
                )
                connection.execute(
                    text("""
                        INSERT INTO app.review_steps
                        (review_step_id,review_id,job_id,step_code,step_name,step_status,
                         sequence_no,timeout_at,timeout_seconds)
                        VALUES (:id,:review_id,:job_id,:code,:name,:status,:sequence,:timeout,:seconds)
                    """),
                    [
                        {
                            "id": step.review_step_id,
                            "review_id": review.review_id,
                            "job_id": job.job_id,
                            "code": step.step_code,
                            "name": step.step_name,
                            "status": step.status,
                            "sequence": step.sequence_no,
                            "timeout": step.timeout_at,
                            "seconds": int((step.timeout_at - review.requested_at).total_seconds())
                            if step.timeout_at
                            else None,
                        }
                        for step in bundle.steps
                    ],
                )
                connection.execute(
                    text(
                        "UPDATE app.advertisements SET latest_review_id=:review_id, review_status='ANALYSIS_REQUESTED', updated_at=:now WHERE advertisement_id=:advertisement_id"
                    ),
                    {
                        "review_id": review.review_id,
                        "advertisement_id": review.advertisement_id,
                        "now": review.requested_at,
                    },
                )
        except Exception as exc:
            if "uk_reviews_active_advertisement" in str(exc):
                raise ValueError("REVIEW_ALREADY_RUNNING") from exc
            raise

    def get(self, review_id: str) -> ReviewBundle | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT r.*,j.job_id,j.job_type,j.job_status,j.progress_rate,j.current_step,
                           j.retry_count,j.max_retries,j.next_retry_at,j.timeout_at,
                           j.failed_reason_code,j.failed_reason,j.is_retryable,
                           COALESCE(j.heartbeat_at,j.started_at,j.created_at) AS job_updated_at
                      FROM app.reviews r JOIN app.review_jobs j USING (review_id)
                     WHERE r.review_id=:review_id
                """),
                {"review_id": review_id},
            ).first()
            if row is None:
                return None
            step_rows = connection.execute(
                text(
                    "SELECT * FROM app.review_steps WHERE review_id=:review_id ORDER BY sequence_no"
                ),
                {"review_id": review_id},
            ).all()
        item = row._mapping
        review = Review(
            review_id=item["review_id"],
            advertisement_id=item["advertisement_id"],
            parent_review_id=item["parent_review_id"],
            review_round=item["review_round"],
            status=item["review_status"],
            standard_effective_date=item["standard_effective_date"],
            standard_version_ids=tuple(item["applied_standard_version_ids"] or ()),
            review_types=tuple(item["review_types"] or ()),
            include_suggestion=item["include_suggestion"],
            include_opinion_draft=item["include_opinion_draft"],
            request_memo=item["request_memo"],
            requested_at=item["requested_at"],
            requested_by=item["requested_by"],
            completed_at=item["completed_at"],
            overall_risk_level=item["overall_risk_level"],
        )
        job = ReviewJob(
            job_id=item["job_id"],
            review_id=item["review_id"],
            job_type=item["job_type"],
            status=item["job_status"],
            progress_rate=float(item["progress_rate"]),
            current_step=item["current_step"],
            retry_count=item["retry_count"],
            max_retries=item["max_retries"],
            next_retry_at=item["next_retry_at"],
            timeout_at=item["timeout_at"],
            failed_reason_code=item["failed_reason_code"],
            failed_reason=item["failed_reason"],
            is_retryable=item["is_retryable"],
            updated_at=item["job_updated_at"],
        )
        steps = [
            ReviewStep(
                review_step_id=step._mapping["review_step_id"],
                step_code=step._mapping["step_code"],
                step_name=step._mapping["step_name"],
                status=step._mapping["step_status"],
                sequence_no=step._mapping["sequence_no"],
                timeout_at=step._mapping["timeout_at"],
                failed_reason_code=step._mapping["failed_reason_code"],
            )
            for step in step_rows
        ]
        return ReviewBundle(review, job, steps)

    def list(self, advertisement_id: str) -> list[Review]:
        with self._engine.connect() as connection:
            ids = connection.execute(
                text(
                    "SELECT review_id FROM app.reviews WHERE advertisement_id=:id ORDER BY review_round DESC"
                ),
                {"id": advertisement_id},
            ).scalars()
            review_ids = list(ids)
        return [bundle.review for review_id in review_ids if (bundle := self.get(review_id))]


class ReviewService:
    def __init__(
        self,
        repository: ReviewRepository,
        advertisements: AdvertisementService,
        queue: ReviewQueue,
        *,
        now: Callable[[], datetime] | None = None,
        identifier: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.advertisements = advertisements
        self.queue = queue
        self._now = now or (lambda: datetime.now(UTC))
        self._identifier = identifier or (lambda prefix: f"{prefix}-{secrets.token_hex(12)}")

    def request(
        self,
        actor: CurrentUser,
        advertisement_id: str,
        *,
        standard_effective_date: date | None,
        review_types: tuple[str, ...] | None,
        include_suggestion: bool,
        include_opinion_draft: bool,
        request_memo: str | None,
        trace_id: str,
        parent_review_id: str | None = None,
        job_type: str = "REVIEW_ANALYSIS",
    ) -> ReviewBundle:
        self.advertisements.get(actor, advertisement_id, trace_id)
        if self.repository.active_review_id(advertisement_id):
            raise ServiceError(409, "REVIEW_ALREADY_RUNNING", "이미 진행 중인 검토가 있습니다.")
        now = self._now()
        review_id = self._identifier("REV")
        job_id = self._identifier("JOB")
        review = Review(
            review_id=review_id,
            advertisement_id=advertisement_id,
            parent_review_id=parent_review_id,
            review_round=self.repository.next_round(advertisement_id),
            status="ANALYSIS_REQUESTED",
            standard_effective_date=standard_effective_date or now.date(),
            standard_version_ids=(),
            review_types=review_types or DEFAULT_REVIEW_TYPES,
            include_suggestion=include_suggestion,
            include_opinion_draft=include_opinion_draft,
            request_memo=request_memo,
            requested_at=now,
            requested_by=actor.user_id,
        )
        job = ReviewJob(
            job_id=job_id,
            review_id=review_id,
            job_type=job_type,
            status="PENDING",
            progress_rate=0,
            retry_count=0,
            max_retries=3,
            timeout_at=now + timedelta(minutes=30),
            updated_at=now,
        )
        steps = [
            ReviewStep(uuid4(), code, name, "PENDING", index, now + timedelta(seconds=seconds))
            for index, (code, name, seconds) in enumerate(STEP_DEFINITIONS, 1)
        ]
        bundle = ReviewBundle(review, job, steps)
        try:
            self.repository.add(bundle)
        except ValueError as exc:
            if str(exc) == "REVIEW_ALREADY_RUNNING":
                raise ServiceError(409, str(exc), "이미 진행 중인 검토가 있습니다.") from exc
            raise
        self.queue.publish(
            ReviewQueueMessage(
                job_id=job_id,
                review_id=review_id,
                job_type=job_type,
                correlation_id=trace_id,
                idempotency_key=job_id,
            )
        )
        return bundle

    def list(self, actor: CurrentUser, advertisement_id: str, trace_id: str) -> list[Review]:
        self.advertisements.get(actor, advertisement_id, trace_id)
        return self.repository.list(advertisement_id)

    def status(self, actor: CurrentUser, review_id: str, trace_id: str) -> ReviewBundle:
        bundle = self.repository.get(review_id)
        if bundle is None:
            raise ServiceError(404, "NOT_FOUND", "요청한 검토를 찾을 수 없습니다.")
        self.advertisements.get(actor, bundle.review.advertisement_id, trace_id)
        return bundle

    def rerun(
        self,
        actor: CurrentUser,
        review_id: str,
        *,
        reason: str,
        review_types: tuple[str, ...] | None,
        trace_id: str,
    ) -> ReviewBundle:
        previous = self.status(actor, review_id, trace_id)
        if previous.job.status in ACTIVE_JOB_STATUSES:
            raise ServiceError(409, "REVIEW_ALREADY_RUNNING", "이미 진행 중인 검토가 있습니다.")
        return self.request(
            actor,
            previous.review.advertisement_id,
            standard_effective_date=previous.review.standard_effective_date,
            review_types=review_types or previous.review.review_types,
            include_suggestion=previous.review.include_suggestion,
            include_opinion_draft=previous.review.include_opinion_draft,
            request_memo=reason,
            trace_id=trace_id,
            parent_review_id=previous.review.review_id,
            job_type="RE_REVIEW",
        )
