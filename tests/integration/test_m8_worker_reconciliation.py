"""Opt-in actual PostgreSQL + Redis worker reconciliation evidence.

Apply migrations, then set M8_LIVE_DATABASE_URL and M8_LIVE_REDIS_URL. The
test uses synthetic identifiers only and does not invoke any parser provider.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis import Redis
from sqlalchemy import create_engine, text

from nh_ad_worker.postgres import PostgresJobRepository
from nh_ad_worker.queue import RedisJobQueue
from nh_ad_worker.runtime import JobRunner


class UnusedProcessor:
    def process(self, payload: dict[str, object]) -> str:
        raise AssertionError(f"reconciliation must not process payloads: {payload}")


class FailOnceQueue:
    def __init__(self, queue: RedisJobQueue) -> None:
        self.queue = queue
        self.failed = False

    def pop(self, timeout: int = 1) -> dict[str, object] | None:
        return self.queue.pop(timeout)

    def publish(self, payload: dict[str, str]) -> None:
        if not self.failed:
            self.failed = True
            raise OSError("synthetic Redis publish outage")
        self.queue.publish(payload)

    def close(self) -> None:
        self.queue.close()


def test_actual_postgres_redis_reconciles_publish_failure_and_stale_job() -> None:
    database_url = os.getenv("M8_LIVE_DATABASE_URL")
    redis_url = os.getenv("M8_LIVE_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("set M8_LIVE_DATABASE_URL and M8_LIVE_REDIS_URL")

    suffix = uuid4().hex[:10]
    department_id = f"DPT-M8-{suffix}"
    user_id = f"USR-M8-{suffix}"
    advertisement_id = f"ADV-M8-{suffix}"
    review_id = f"REV-M8-{suffix}"
    job_id = f"JOB-M8-{suffix}"
    queue_name = f"m8-worker-{suffix}"
    now = datetime.now(UTC)
    engine = create_engine(database_url, pool_pre_ping=True)
    redis = Redis.from_url(redis_url, decode_responses=True)
    queue = RedisJobQueue(redis_url, queue_name=queue_name)
    failing_queue = FailOnceQueue(queue)
    repository = PostgresJobRepository(engine, lambda _bucket, _key: b"")
    runner = JobRunner(failing_queue, UnusedProcessor(), repository)

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO app.departments(department_id,department_name) "
                    "VALUES (:id,'M8 Worker Synthetic')"
                ),
                {"id": department_id},
            )
            connection.execute(
                text("""
                    INSERT INTO app.users
                    (user_id,auth_provider,user_name,email,department_id,user_status)
                    VALUES (:id,'LOCAL','M8 Worker Synthetic',:email,:department,'ACTIVE')
                """),
                {
                    "id": user_id,
                    "email": f"{suffix}@example.invalid",
                    "department": department_id,
                },
            )
            connection.execute(
                text("""
                    INSERT INTO app.advertisements
                    (advertisement_id,advertisement_name,product_group,advertisement_type,
                     department_id,owner_user_id,review_status,created_by)
                    VALUES (:id,'M8 worker synthetic','SAVINGS','MOBILE_BANNER',
                     :department,:user,'ANALYSIS_REQUESTED',:user)
                """),
                {"id": advertisement_id, "department": department_id, "user": user_id},
            )
            connection.execute(
                text("""
                    INSERT INTO app.reviews
                    (review_id,advertisement_id,review_round,review_status,
                     standard_effective_date,applied_standard_version_ids,review_types,
                     include_suggestion,include_opinion_draft,requested_at,requested_by,
                     created_at,updated_at)
                    VALUES (:review,:advertisement,1,'ANALYSIS_REQUESTED',:effective,
                     '[]'::jsonb,'["OCR_QUALITY"]'::jsonb,false,false,:created,:user,
                     :created,:created)
                """),
                {
                    "review": review_id,
                    "advertisement": advertisement_id,
                    "effective": now.date(),
                    "created": now - timedelta(minutes=5),
                    "user": user_id,
                },
            )
            connection.execute(
                text("""
                    INSERT INTO app.review_jobs
                    (job_id,review_id,job_type,job_status,queue_name,progress_rate,
                     retry_count,max_retries,is_retryable,created_at)
                    VALUES (:job,:review,'REVIEW_ANALYSIS','PENDING',:queue,0,0,3,true,:created)
                """),
                {
                    "job": job_id,
                    "review": review_id,
                    "queue": queue_name,
                    "created": now - timedelta(minutes=5),
                },
            )

        assert runner.recover_stale(now) == 0
        with engine.connect() as connection:
            pending = connection.execute(
                text("SELECT job_status,enqueued_at FROM app.review_jobs WHERE job_id=:job"),
                {"job": job_id},
            ).one()
        assert pending._mapping["job_status"] == "PENDING"
        assert pending._mapping["enqueued_at"] == now
        assert redis.llen(queue_name) == 0

        assert runner.recover_stale(now + timedelta(minutes=1)) == 0
        assert runner.recover_stale(now + timedelta(minutes=3)) == 1
        recovered = queue.pop(timeout=1)
        assert recovered == {
            "messageVersion": "review-job-v1",
            "jobId": job_id,
            "reviewId": review_id,
            "jobType": "REVIEW_ANALYSIS",
            "correlationId": f"recovery-{job_id}",
            "idempotencyKey": job_id,
        }

        stale_now = now + timedelta(minutes=6)
        with engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET job_status='RUNNING',heartbeat_at=:heartbeat,locked_by='dead-worker'
                     WHERE job_id=:job
                """),
                {"heartbeat": stale_now - timedelta(minutes=3), "job": job_id},
            )
        assert runner.recover_stale(stale_now) == 1
        assert queue.pop(timeout=1)["jobId"] == job_id  # type: ignore[index]
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT job_status FROM app.review_jobs WHERE job_id=:job"),
                    {"job": job_id},
                ).scalar_one()
                == "STALE"
            )
    finally:
        redis.delete(queue_name)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app.advertisements SET latest_review_id=NULL WHERE advertisement_id=:id"
                ),
                {"id": advertisement_id},
            )
            connection.execute(
                text("DELETE FROM app.reviews WHERE review_id=:id"), {"id": review_id}
            )
            connection.execute(
                text("DELETE FROM app.advertisements WHERE advertisement_id=:id"),
                {"id": advertisement_id},
            )
            connection.execute(text("DELETE FROM app.users WHERE user_id=:id"), {"id": user_id})
            connection.execute(
                text("DELETE FROM app.departments WHERE department_id=:id"),
                {"id": department_id},
            )
        queue.close()
        redis.close()
        engine.dispose()
