from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from time import monotonic, sleep

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from nh_ad_parser_contracts import DocumentInput
from nh_ad_worker.jobs import InMemoryJobRepository, QueueMessage, WorkerJob
import nh_ad_worker.main as worker_main
from nh_ad_worker.main import create_app
from nh_ad_worker.runtime import JobRunner
from nh_ad_worker.settings import Settings


class StubReadiness:
    async def ready(self) -> bool:
        return True


class StubProcessor:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def process(self, payload: dict[str, object]) -> str:
        self.payloads.append(payload)
        return "COMPLETED"


class StubQueue:
    def __init__(self, *, fail_publish_once: bool = False) -> None:
        self.fail_publish_once = fail_publish_once
        self.published: list[dict[str, str]] = []
        self.closed = False

    def pop(self, timeout: int = 1) -> dict[str, object] | None:
        return None

    def publish(self, payload: dict[str, str]) -> None:
        if self.fail_publish_once:
            self.fail_publish_once = False
            raise OSError("redis unavailable")
        self.published.append(payload)

    def close(self) -> None:
        self.closed = True


class LifecycleRunner:
    def __init__(self, *, exit_immediately: bool = False) -> None:
        self.started = Event()
        self.stopped = Event()
        self.closed = False
        self.exit_immediately = exit_immediately

    def run_forever(self) -> None:
        self.started.set()
        if not self.exit_immediately:
            self.stopped.wait()

    def stop(self) -> None:
        self.stopped.set()

    def close(self) -> None:
        self.closed = True


class OutageRepository(InMemoryJobRepository):
    def __init__(self) -> None:
        super().__init__()
        self.runner: JobRunner | None = None
        self.recovery_calls = 0

    def recover_stale(
        self, *, now: datetime, stale_before: datetime
    ) -> list[QueueMessage]:
        self.recovery_calls += 1
        if self.recovery_calls == 1:
            raise OSError("postgres unavailable")
        assert self.runner is not None
        self.runner.stop()
        return []


def worker_job(job_id: str, *, created_at: datetime) -> WorkerJob:
    return WorkerJob(
        job_id,
        f"REV-{job_id}",
        DocumentInput(
            source_file_id=f"FILE-{job_id}",
            review_id=f"REV-{job_id}",
            file_name="synthetic.png",
            mime_type="image/png",
            body=b"synthetic",
        ),
        created_at=created_at,
    )


def test_publish_failure_remains_recoverable_after_database_lease_expires() -> None:
    now = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
    job = worker_job("JOB-PUBLISH", created_at=now - timedelta(minutes=5))
    repository = InMemoryJobRepository([job])
    queue = StubQueue(fail_publish_once=True)
    runner = JobRunner(queue, StubProcessor(), repository)

    assert runner.recover_stale(now) == 0
    assert job.status == "PENDING" and job.enqueued_at == now
    assert runner.recover_stale(now + timedelta(minutes=1)) == 0
    assert runner.recover_stale(now + timedelta(minutes=3)) == 1
    assert queue.published == [
        {
            "messageVersion": "review-job-v1",
            "jobId": job.job_id,
            "reviewId": job.review_id,
            "jobType": "REVIEW_ANALYSIS",
            "correlationId": f"recovery-{job.job_id}",
            "idempotencyKey": job.job_id,
        }
    ]


def test_recovery_outage_uses_bounded_backoff_without_killing_consumer() -> None:
    repository = OutageRepository()
    runner = JobRunner(
        StubQueue(),
        StubProcessor(),
        repository,
        recovery_interval_seconds=0,
        recovery_backoff_seconds=0.01,
    )
    repository.runner = runner
    consumer = Thread(target=runner.run_forever)

    consumer.start()
    consumer.join(1)

    assert not consumer.is_alive()
    assert repository.recovery_calls == 2


def test_stale_and_due_retry_are_requeued_but_future_retry_is_not() -> None:
    now = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    stale = worker_job("JOB-STALE", created_at=now - timedelta(minutes=10))
    repository = InMemoryJobRepository([stale])
    message = QueueMessage(
        stale.job_id,
        stale.review_id,
        "REVIEW_ANALYSIS",
        "corr-stale",
        stale.job_id,
    )
    assert repository.claim(message, worker_id="crashed", now=now - timedelta(minutes=3)) is stale

    due = worker_job("JOB-DUE", created_at=now - timedelta(minutes=10))
    due.status = "RETRY_PENDING"
    due.next_retry_at = now
    future = worker_job("JOB-FUTURE", created_at=now - timedelta(minutes=10))
    future.status = "RETRY_PENDING"
    future.next_retry_at = now + timedelta(minutes=1)
    repository.jobs.update({due.job_id: due, future.job_id: future})
    queue = StubQueue()
    runner = JobRunner(queue, StubProcessor(), repository)

    assert runner.recover_stale(now) == 2
    assert stale.status == "STALE"
    assert {payload["jobId"] for payload in queue.published} == {stale.job_id, due.job_id}


def test_lifespan_supervises_runner_and_shutdown_closes_it() -> None:
    runner = LifecycleRunner()
    app = create_app(
        Settings(app_env="test"),
        StubReadiness(),
        runner_factory=lambda _settings: runner,
    )

    with TestClient(app) as client:
        assert runner.started.wait(1)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["consumer"] == "ready"

    assert runner.stopped.is_set()
    assert runner.closed


def test_dead_or_missing_infrastructure_consumer_never_reports_ready() -> None:
    dead = LifecycleRunner(exit_immediately=True)
    dead_app = create_app(
        Settings(app_env="test"),
        StubReadiness(),
        runner_factory=lambda _settings: dead,
    )
    with TestClient(dead_app) as client:
        assert dead.started.wait(1)
        deadline = monotonic() + 1
        response = client.get("/ready")
        while response.status_code != 503 and monotonic() < deadline:
            sleep(0.01)
            response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "queue": "ready",
            "consumer": "not_ready",
        }

    missing_infrastructure_app = create_app(Settings(app_env="test"), StubReadiness())
    with TestClient(missing_infrastructure_app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["consumer"] == "not_ready"


def test_default_production_factory_reports_ready_when_composed_consumer_is_live(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = LifecycleRunner()
    monkeypatch.setattr(worker_main, "compose_job_runner", lambda _settings, _router: runner)
    app = create_app(Settings(app_env="test"), StubReadiness())

    with TestClient(app) as client:
        assert runner.started.wait(1)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "queue": "ready",
            "consumer": "ready",
        }

    assert runner.stopped.is_set()
    assert runner.closed
