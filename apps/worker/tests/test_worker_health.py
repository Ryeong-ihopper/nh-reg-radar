from fastapi.testclient import TestClient
from pytest import MonkeyPatch, raises
from redis.exceptions import ConnectionError as RedisConnectionError

from nh_ad_worker.main import create_app
from nh_ad_worker.queue import RedisQueueReadiness
from nh_ad_worker.settings import Settings


class StubQueue:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    async def ready(self) -> bool:
        return self._ready


class UnavailableRedis:
    async def ping(self) -> bool:
        raise RedisConnectionError("synthetic Redis outage")

    async def aclose(self) -> None:
        return None


class AvailableRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class UnexpectedRedisFailure:
    async def ping(self) -> bool:
        raise RuntimeError("unexpected readiness bug")

    async def aclose(self) -> None:
        return None


def test_health_does_not_depend_on_queue_readiness() -> None:
    app = create_app(Settings(app_env="test"), StubQueue(ready=False), runner_factory=None)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "worker",
        "environment": "test",
    }


def test_readiness_reports_queue_availability() -> None:
    app = create_app(Settings(app_env="test"), StubQueue(ready=True), runner_factory=None)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "queue": "ready", "consumer": "ready"}


def test_readiness_fails_when_queue_is_unavailable() -> None:
    app = create_app(Settings(app_env="test"), StubQueue(ready=False), runner_factory=None)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "queue": "not_ready",
        "consumer": "ready",
    }


def test_redis_transport_failure_reports_structured_not_ready(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nh_ad_worker.queue.Redis.from_url",
        lambda *args, **kwargs: UnavailableRedis(),
    )
    queue = RedisQueueReadiness("redis://synthetic-outage:6379/0")
    app = create_app(Settings(app_env="test"), queue, runner_factory=None)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "queue": "not_ready",
        "consumer": "ready",
    }


def test_redis_readiness_preserves_successful_ping(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nh_ad_worker.queue.Redis.from_url",
        lambda *args, **kwargs: AvailableRedis(),
    )
    queue = RedisQueueReadiness("redis://synthetic-ready:6379/0")
    app = create_app(Settings(app_env="test"), queue, runner_factory=None)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "queue": "ready",
        "consumer": "ready",
    }


def test_redis_readiness_does_not_hide_non_redis_errors(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nh_ad_worker.queue.Redis.from_url",
        lambda *args, **kwargs: UnexpectedRedisFailure(),
    )
    queue = RedisQueueReadiness("redis://synthetic-bug:6379/0")
    app = create_app(Settings(app_env="test"), queue, runner_factory=None)

    with (
        TestClient(app) as client,
        raises(
            RuntimeError,
            match="unexpected readiness bug",
        ),
    ):
        client.get("/ready")
