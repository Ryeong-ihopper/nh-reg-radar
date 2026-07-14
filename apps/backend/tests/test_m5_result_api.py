from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient

from conftest import JWT_SECRET, Clock, login
from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.domain import Advertisement, AdvertisementFile
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.results import (
    InMemoryResultRepository,
    ResultAnnotation,
    ResultEvidence,
    ResultItem,
    ResultService,
)
from nh_ad_backend.reviews import InMemoryReviewQueue, InMemoryReviewRepository, ReviewService
from nh_ad_backend.settings import Settings


def score_detail(evidence_status: str = "CONNECTED") -> dict[str, object]:
    return {
        "rule": {"matched": True, "ruleIds": ["RULE-M5-001"], "severity": "HIGH"},
        "rag": {
            "topRelevanceScore": 0.91 if evidence_status == "CONNECTED" else None,
            "evidenceCount": 1 if evidence_status == "CONNECTED" else 0,
            "evidenceSufficient": evidence_status == "CONNECTED",
            "status": evidence_status,
            "failureCode": None,
        },
        "llm": {
            "schemaVersion": "review-structured-output-v1",
            "status": "NOT_RUN",
            "decision": None,
            "confidence": None,
        },
        "parser": {"confidenceStatus": "READABLE"},
        "final": {"riskLevel": "HIGH", "decisionRule": "RULE_EXPLICIT_VIOLATION"},
    }


def m5_client(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> tuple[TestClient, InMemoryReviewRepository, InMemoryResultRepository]:
    repository.add_advertisement(
        Advertisement(
            "ADV-M5-0001",
            "M5 fixture",
            "SAVINGS",
            "MOBILE_BANNER",
            None,
            "DPT-A",
            "user-a",
            "UPLOADED",
            None,
            clock(),
            files=[
                AdvertisementFile(
                    "FILE-M5-0001",
                    "png",
                    "fixture.png",
                    "m5/fixture.png",
                    "image/png",
                    9,
                    "m5-checksum",
                )
            ],
        )
    )
    reviews = InMemoryReviewRepository()
    identifiers = iter(("REV-M5-0001", "JOB-M5-0001"))
    review_service = ReviewService(
        reviews,
        services.advertisements,
        InMemoryReviewQueue(),
        now=clock,
        identifier=lambda _prefix: next(identifiers),
    )
    results = InMemoryResultRepository()
    app = create_app(
        Settings(
            app_env="test",
            jwt_secret=JWT_SECRET,
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        ),
        replace(
            services,
            reviews=review_service,
            results=ResultService(results, review_service),
        ),
    )
    return TestClient(app), reviews, results


def add_result(results: InMemoryResultRepository, review_id: str) -> None:
    evidence = ResultEvidence(
        "EVD-M5-0001",
        "ECH-M5-0001",
        "STDVER-M5-0001",
        "GUIDELINE",
        "광고 표현 기준",
        None,
        "절대적 표현은 사용할 수 없습니다.",
        1,
        0.91,
        "HYBRID",
    )
    annotation = ResultAnnotation(
        "ANN-M5-0001",
        "ITEM-M5-0001",
        "FILE-M5-0001",
        "png",
        "MISLEADING_EXPRESSION",
        "HIGH",
        "최고 연 3.5% 금리",
        "BOX",
        "LOCATED",
        0.94,
        "confidence-thresholds-v1",
        "NORMALIZED_COORDINATE",
        1,
        {
            "sourceWidth": 1000,
            "sourceHeight": 500,
            "sourceUnit": "px",
            "x": 100,
            "y": 50,
            "width": 400,
            "height": 50,
            "normalizedX": 0.1,
            "normalizedY": 0.1,
            "normalizedWidth": 0.4,
            "normalizedHeight": 0.1,
            "rotation": 0,
            "coordinateConfidence": 0.94,
        },
        matched_text="최고 연 3.5% 금리",
    )
    results.add(
        ResultItem(
            "ITEM-M5-0001",
            review_id,
            "MISLEADING_EXPRESSION",
            "최고 연 3.5% 금리",
            "NEEDS_REVISION",
            "HIGH",
            "risk-policy-v1",
            ("MISLEADING_ABSOLUTE_EXPRESSION", "RULE_EXPLICIT_VIOLATION"),
            score_detail(),
            "CONNECTED",
            None,
            "객관적 조건이 없는 최상급 표현입니다.",
            "조건과 적용 범위를 표시해 주세요.",
            "RULE",
            "rule-config-v1",
            1,
            (evidence,),
            annotation,
        )
    )


def test_m5_summary_item_evidence_and_annotation_api_are_scoped(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    client, reviews, results = m5_client(services, repository, clock)
    with client:
        token, _ = login(client)
        accepted = client.post(
            "/api/v1/advertisements/ADV-M5-0001/reviews",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()
        bundle = reviews.get(accepted["reviewId"])
        assert bundle is not None
        bundle.review.status = "REVIEW_COMPLETED"
        bundle.review.completed_at = clock.value + timedelta(seconds=2)
        bundle.review.standard_version_ids = ("STDVER-M5-0001",)
        bundle.job.status = "COMPLETED"
        add_result(results, bundle.review.review_id)

        summary = client.get(
            f"/api/v1/reviews/{bundle.review.review_id}/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert summary.status_code == 200, summary.text
        assert summary.json()["overallRiskLevel"] == "HIGH"
        assert summary.json()["topRisks"][0]["evidenceStatus"] == "CONNECTED"

        items = client.get(
            f"/api/v1/reviews/{bundle.review.review_id}/items?evidenceRequired=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert items.status_code == 200
        assert items.json()["totalElements"] == 1

        detail = client.get(
            f"/api/v1/reviews/{bundle.review.review_id}/items/ITEM-M5-0001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == 200
        assert detail.json()["riskRationale"]["policyVersion"] == "risk-policy-v1"
        assert detail.json()["evidences"][0]["standardVersionId"] == "STDVER-M5-0001"

        annotations = client.get(
            f"/api/v1/reviews/{bundle.review.review_id}/annotations?pageNo=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert annotations.status_code == 200
        assert annotations.json()["annotations"][0]["annotationDisplayMode"] == "BOX"

        other, _ = login(client, "b@example.com")
        denied = client.get(
            f"/api/v1/reviews/{bundle.review.review_id}/summary",
            headers={"Authorization": f"Bearer {other}"},
        )
        assert denied.status_code == 403


def test_result_api_does_not_hide_search_failure(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    client, reviews, results = m5_client(services, repository, clock)
    with client:
        token, _ = login(client)
        review_id = client.post(
            "/api/v1/advertisements/ADV-M5-0001/reviews",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()["reviewId"]
        bundle = reviews.get(review_id)
        assert bundle is not None
        bundle.review.completed_at = clock.value
        bundle.job.status = "COMPLETED"
        add_result(results, review_id)
        original = results.get_item(review_id, "ITEM-M5-0001")
        assert original is not None
        results._items[0] = replace(  # noqa: SLF001 - deterministic in-memory fixture mutation
            original,
            evidence_status="SEARCH_UNAVAILABLE",
            evidence_failure_code="RAG_SEARCH_FAILED",
            evidences=(),
            risk_score_detail=score_detail("SEARCH_UNAVAILABLE"),
        )

        response = client.get(
            f"/api/v1/reviews/{review_id}/items/ITEM-M5-0001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["riskLevel"] == "HIGH"
        assert response.json()["evidenceStatus"] == "SEARCH_UNAVAILABLE"
        assert response.json()["evidenceFailureCode"] == "RAG_SEARCH_FAILED"
