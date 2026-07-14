"""Runnable review-job consumer orchestration."""

from datetime import UTC, datetime, timedelta

from nh_ad_worker.jobs import JobRepository, ParserJobProcessor
from nh_ad_worker.queue import RedisJobQueue


class JobRunner:
    def __init__(
        self,
        queue: RedisJobQueue,
        processor: ParserJobProcessor,
        repository: JobRepository,
    ) -> None:
        self.queue = queue
        self.processor = processor
        self.repository = repository

    def run_once(self, timeout: int = 1) -> str | None:
        payload = self.queue.pop(timeout)
        return None if payload is None else self.processor.process(payload)

    def recover_stale(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        messages = self.repository.recover_stale(
            now=current,
            stale_before=current - timedelta(minutes=2),
        )
        for message in messages:
            self.queue.publish(
                {
                    "messageVersion": message.message_version,
                    "jobId": message.job_id,
                    "reviewId": message.review_id,
                    "jobType": message.job_type,
                    "correlationId": message.correlation_id,
                    "idempotencyKey": message.idempotency_key,
                }
            )
        return len(messages)
