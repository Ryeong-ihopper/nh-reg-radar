"""Runnable review-job consumer orchestration."""

import logging
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic
from typing import Protocol

from nh_ad_worker.jobs import JobRepository


LOGGER = logging.getLogger(__name__)


class JobQueue(Protocol):
    def pop(self, timeout: int = 1) -> dict[str, object] | None: ...
    def publish(self, payload: dict[str, str]) -> None: ...
    def close(self) -> None: ...


class JobProcessor(Protocol):
    def process(self, payload: dict[str, object]) -> str: ...


class Runner(Protocol):
    def run_forever(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class JobRunner:
    def __init__(
        self,
        queue: JobQueue,
        processor: JobProcessor,
        repository: JobRepository,
        *,
        poll_timeout_seconds: int = 1,
        recovery_interval_seconds: float = 30.0,
        stale_after: timedelta = timedelta(minutes=2),
    ) -> None:
        self.queue = queue
        self.processor = processor
        self.repository = repository
        self.poll_timeout_seconds = poll_timeout_seconds
        self.recovery_interval_seconds = recovery_interval_seconds
        self.stale_after = stale_after
        self._stop = Event()

    def run_once(self, timeout: int = 1) -> str | None:
        payload = self.queue.pop(timeout)
        return None if payload is None else self.processor.process(payload)

    def recover_stale(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        messages = self.repository.recover_stale(
            now=current,
            stale_before=current - self.stale_after,
        )
        published = 0
        for message in messages:
            payload = {
                "messageVersion": message.message_version,
                "jobId": message.job_id,
                "reviewId": message.review_id,
                "jobType": message.job_type,
                "correlationId": message.correlation_id,
                "idempotencyKey": message.idempotency_key,
            }
            try:
                self.queue.publish(payload)
                published += 1
            except Exception:
                LOGGER.exception(
                    "job delivery reconciliation failed",
                    extra={"job_id": message.job_id, "review_id": message.review_id},
                )
        return published

    def run_forever(self) -> None:
        next_recovery = 0.0
        while not self._stop.is_set():
            current = monotonic()
            if current >= next_recovery:
                self.recover_stale()
                next_recovery = current + self.recovery_interval_seconds
            try:
                self.run_once(self.poll_timeout_seconds)
            except Exception:
                LOGGER.exception("job consumer iteration failed")

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self.queue.close()
        self.repository.close()
