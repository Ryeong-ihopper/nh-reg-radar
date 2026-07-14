from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient

from conftest import JWT_SECRET, Clock, login
from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.domain import Advertisement
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.reviews import (
    InMemoryReviewQueue,
    InMemoryReviewRepository,
    RETRY_DELAYS,
    ReviewService,
)
from nh_ad_backend.settings import Settings


def m4_client(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> tuple[TestClient, InMemoryReviewRepository, InMemoryReviewQueue]:
    repository.add_advertisement(
        Advertisement(
            advertisement_id="ADV-M4-0001",
            advertisement_name="M4 fixture",
            product_group="SAVINGS",
            advertisement_type="MOBILE_BANNER",
            channel_type=None,
            department_id="DPT-A",
            owner_user_id="user-a",
            review_status="UPLOADED",
            memo=None,
            created_at=clock(),
        )
    )
    reviews = InMemoryReviewRepository()
    queue = InMemoryReviewQueue()
    counter = iter(range(1, 20))
    review_service = ReviewService(
        reviews,
        services.advertisements,
        queue,
        now=clock,
        identifier=lambda prefix: f"{prefix}-M4-{next(counter):04d}",
    )
    application = create_app(
        Settings(
            app_env="test",
            jwt_secret=JWT_SECRET,
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        ),
        replace(services, reviews=review_service),
    )
    return TestClient(application), reviews, queue


def test_review_request_progress_queue_minimality_and_scope(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    client, reviews, queue = m4_client(services, repository, clock)
    with client:
        token, _ = login(client)
        accepted = client.post(
            "/api/v1/advertisements/ADV-M4-0001/reviews",
            headers={"Authorization": f"Bearer {token}", "x-request-id": "req-m4"},
            json={"reviewTypes": ["OCR_QUALITY"], "includeSuggestion": False},
        )
        assert accepted.status_code == 202, accepted.text
        payload = accepted.json()
        assert payload["reviewStatus"] == "ANALYSIS_REQUESTED"
        assert set(queue.messages[0]) == {
            "messageVersion",
            "jobId",
            "reviewId",
            "jobType",
            "correlationId",
            "idempotencyKey",
        }
        assert "raw" not in str(queue.messages).casefold()
        assert "object" not in str(queue.messages).casefold()

        duplicate = client.post(
            "/api/v1/advertisements/ADV-M4-0001/reviews",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "REVIEW_ALREADY_RUNNING"

        status = client.get(
            f"/api/v1/reviews/{payload['reviewId']}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status.status_code == 200
        assert status.json()["jobStatus"] == "PENDING"
        assert status.json()["maxRetries"] == 3
        assert len(status.json()["steps"]) == 6

        other, _ = login(client, "b@example.com")
        denied = client.get(
            f"/api/v1/reviews/{payload['reviewId']}/status",
            headers={"Authorization": f"Bearer {other}"},
        )
        assert denied.status_code == 403
        assert reviews.get(payload["reviewId"]) is not None


def test_rerun_creates_immutable_new_round(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    client, reviews, queue = m4_client(services, repository, clock)
    with client:
        token, _ = login(client)
        first = client.post(
            "/api/v1/advertisements/ADV-M4-0001/reviews",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()
        original = reviews.get(first["reviewId"])
        assert original is not None
        original.job.status = "FAILED_FINAL"
        original.job.is_retryable = False
        original.review.status = "REVIEW_FAILED"

        rerun = client.post(
            f"/api/v1/reviews/{first['reviewId']}/rerun",
            headers={"Authorization": f"Bearer {token}"},
            json={"reason": "quality confirmation"},
        )
        assert rerun.status_code == 202, rerun.text
        assert rerun.json()["previousReviewId"] == first["reviewId"]
        assert rerun.json()["newReviewId"] != first["reviewId"]
        assert queue.messages[-1]["jobType"] == "RE_REVIEW"

        history = client.get(
            "/api/v1/advertisements/ADV-M4-0001/reviews",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert [item["reviewRound"] for item in history.json()] == [2, 1]


def test_retry_schedule_is_exactly_one_three_ten_minutes() -> None:
    assert RETRY_DELAYS == (
        timedelta(minutes=1),
        timedelta(minutes=3),
        timedelta(minutes=10),
    )
