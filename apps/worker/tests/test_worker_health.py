from fastapi.testclient import TestClient

from nh_ad_worker.main import create_app
from nh_ad_worker.settings import Settings


class StubQueue:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    async def ready(self) -> bool:
        return self._ready


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
