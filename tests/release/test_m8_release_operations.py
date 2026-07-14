from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nh_ad_backend.domain import User
from nh_ad_backend.main import build_services, create_app as create_backend_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.security import TokenService, hash_password
from nh_ad_backend.services import AuthService
from nh_ad_backend.settings import Settings as BackendSettings
from nh_ad_worker.jobs import QueueMessage, redacted_log
from nh_ad_worker.main import create_app as create_worker_app
from nh_ad_worker.runtime import JobRunner
from nh_ad_worker.settings import Settings as WorkerSettings


JWT_SECRET = "synthetic-release-jwt-secret-with-at-least-thirty-two-characters"
PASSWORD = "SyntheticPassword!42"


class UnavailableQueueReadiness:
    async def ready(self) -> bool:
        return False


class FailingPublishQueue:
    def pop(self, timeout: int = 1) -> dict[str, object] | None:
        del timeout
        return None

    def publish(self, payload: dict[str, str]) -> None:
        del payload
        raise OSError("synthetic queue outage")

    def close(self) -> None:
        return None


class RecoveryRepository:
    def recover_stale(
        self, *, now: datetime, stale_before: datetime
    ) -> list[QueueMessage]:
        del now, stale_before
        return [
            QueueMessage(
                job_id="JOB-M8-REDACTED",
                review_id="REV-M8-REDACTED",
                job_type="REVIEW_ANALYSIS",
                correlation_id="corr-m8-release",
                idempotency_key="JOB-M8-REDACTED",
            )
        ]

    def close(self) -> None:
        return None


class NoopProcessor:
    def process(self, payload: dict[str, object]) -> str:
        del payload
        return "COMPLETED"


def test_backend_health_security_headers_and_trace_are_release_safe(tmp_path: Path) -> None:
    services = build_services(
        BackendSettings(
            app_env="test",
            jwt_secret=SecretStr(JWT_SECRET),
            private_storage_path=tmp_path / "objects",
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        )
    )
    application = create_backend_app(
        BackendSettings(
            app_env="prod",
            cors_allowed_origins="https://release.invalid",
        ),
        services,
    )

    with TestClient(application) as client:
        health = client.get("/health", headers={"x-request-id": "req-m8-health"})
        denied = client.get(
            "/api/v1/users/me",
            headers={
                "Authorization": "Bearer synthetic-secret-token",
                "x-request-id": "req-m8-denied",
            },
        )

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "backend", "environment": "prod"}
    assert health.headers["x-request-id"] == "req-m8-health"
    assert health.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert health.headers["content-security-policy"] == (
        "default-src 'self'; frame-ancestors 'none'"
    )
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"

    assert denied.status_code == 401
    assert denied.headers["cache-control"] == "no-store"
    assert denied.json()["traceId"] == "req-m8-denied"
    assert "synthetic-secret-token" not in denied.text
    assert "authorization" not in denied.text.casefold()


def test_audit_event_keeps_trace_metadata_without_credentials_or_personal_data() -> None:
    repository = InMemoryRepository(
        [
            User(
                user_id="user-m8",
                user_name="합성 사용자",
                email="synthetic.user@example.invalid",
                password_hash=hash_password(PASSWORD, salt=b"0123456789abcdef"),
                department_id="DPT-M8",
                department_name="합성 부서",
                roles=("PRODUCT_DEPARTMENT_USER",),
            )
        ]
    )
    service = AuthService(repository, TokenService(JWT_SECRET))

    access_token, refresh_token, _user = service.login(
        "synthetic.user@example.invalid",
        PASSWORD,
        "192.0.2.10",
        "m8-release-test",
        "req-m8-login",
    )
    event = repository.list_audit_events()[0]
    serialized = json.dumps(asdict(event), ensure_ascii=False, default=str)

    assert event.action_type == "LOGIN"
    assert event.result == "SUCCESS"
    assert event.trace_id == "req-m8-login"
    assert event.actor_user_id == "user-m8"
    for forbidden in (
        PASSWORD,
        access_token,
        refresh_token,
        "synthetic.user@example.invalid",
        "합성 사용자",
        "192.0.2.10",
    ):
        assert forbidden not in serialized


def test_worker_readiness_fails_closed_when_queue_is_unavailable() -> None:
    application = create_worker_app(
        WorkerSettings(app_env="test"),
        UnavailableQueueReadiness(),
        runner_factory=None,
    )

    with TestClient(application) as client:
        health = client.get("/health")
        readiness = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert readiness.status_code == 503
    assert readiness.json() == {
        "status": "not_ready",
        "queue": "not_ready",
        "consumer": "ready",
    }


def test_worker_recovery_log_has_structured_ids_and_no_sensitive_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner = JobRunner(
        FailingPublishQueue(),
        NoopProcessor(),
        RecoveryRepository(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.ERROR, logger="nh_ad_worker.runtime"):
        assert runner.recover_stale(datetime(2026, 7, 15, tzinfo=UTC)) == 0

    record = next(
        item for item in caplog.records if item.message == "job delivery reconciliation failed"
    )
    assert record.job_id == "JOB-M8-REDACTED"  # type: ignore[attr-defined]
    assert record.review_id == "REV-M8-REDACTED"  # type: ignore[attr-defined]
    rendered = caplog.text.casefold()
    for forbidden in ("password", "token", "objectkey", "presigned", "customer raw text"):
        assert forbidden not in rendered


def test_worker_queue_log_is_minimal_deterministic_json() -> None:
    payload = {
        "messageVersion": "review-job-v1",
        "jobId": "JOB-M8-LOG",
        "reviewId": "REV-M8-LOG",
        "jobType": "REVIEW_ANALYSIS",
        "correlationId": "corr-m8-log",
        "idempotencyKey": "JOB-M8-LOG",
    }
    rendered = redacted_log(payload)

    assert json.loads(rendered) == {
        "messageVersion": "review-job-v1",
        "jobId": "JOB-M8-LOG",
        "reviewId": "REV-M8-LOG",
        "jobType": "REVIEW_ANALYSIS",
        "correlationId": "corr-m8-log",
    }
    assert "idempotencyKey" not in rendered
    assert "raw" not in rendered.casefold()
    assert "object" not in rendered.casefold()
