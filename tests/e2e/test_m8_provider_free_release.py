"""Deterministic provider-free release proof for M8 E2E-001 through E2E-004."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.domain import User
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
from nh_ad_backend.search import HybridSearch, InMemorySearchBackend
from nh_ad_backend.security import LoginRateLimiter, TokenService, hash_password
from nh_ad_backend.services import AdvertisementService, AuthService
from nh_ad_backend.settings import Settings
from nh_ad_backend.standards import InMemoryStandardRepository, StandardService
from nh_ad_backend.storage import PrivateFileStorage
from nh_ad_backend.support import InMemorySupportRepository, SupportService
from nh_ad_backend.validation import InMemoryValidationRepository, ValidationService


ROOT = Path(__file__).parents[2]
FIXTURE_PATH = ROOT / "fixtures" / "m8" / "provider-free-release-v1.json"
PASSWORD = "SecurePassword!42"
JWT_SECRET = "m8-provider-free-jwt-secret-with-more-than-thirty-two-characters"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


@dataclass
class M8Harness:
    client: TestClient
    fixture: dict[str, Any]
    clock: FixedClock
    repository: InMemoryRepository
    standards: StandardService
    reviews: InMemoryReviewRepository
    results: InMemoryResultRepository
    queue: InMemoryReviewQueue
    support: InMemorySupportRepository
    validation: InMemoryValidationRepository


def _users() -> list[User]:
    password_hash = hash_password(PASSWORD, salt=b"0123456789abcdef")
    return [
        User(
            "user-a",
            "Synthetic Product User",
            "product@example.test",
            password_hash,
            "DPT-A",
            "Synthetic Product Department",
            ("PRODUCT_DEPARTMENT_USER",),
        ),
        User(
            "reviewer",
            "Synthetic Reviewer",
            "reviewer@example.test",
            password_hash,
            "DPT-C",
            "Synthetic Compliance Department",
            ("COMPLIANCE_REVIEWER",),
        ),
        User(
            "standard",
            "Synthetic Standard Manager",
            "standard@example.test",
            password_hash,
            "DPT-C",
            "Synthetic Compliance Department",
            ("STANDARD_MANAGER",),
        ),
    ]


def _identifier(namespace: str) -> Any:
    counters: defaultdict[str, int] = defaultdict(int)

    def next_identifier(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}-{namespace}-{counters[prefix]:04d}"

    return next_identifier


def _harness(tmp_path: Path) -> M8Harness:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    clock = FixedClock(datetime.fromisoformat(fixture["clock"].replace("Z", "+00:00")))
    repository = InMemoryRepository(_users())
    advertisements = AdvertisementService(
        repository,
        PrivateFileStorage(tmp_path / "objects"),
        now=clock,
        identifier=_identifier("M8"),
    )
    standard_repository = InMemoryStandardRepository()
    standards = StandardService(
        standard_repository,
        HybridSearch(
            keyword=InMemorySearchBackend("OPENSEARCH"),
            vector=InMemorySearchBackend("QDRANT"),
        ),
        now=clock,
        identifier=_identifier("M8"),
        environment="test",
        audit_sink=repository.add_audit_event,
    )
    review_repository = InMemoryReviewRepository()
    queue = InMemoryReviewQueue()
    reviews = ReviewService(
        review_repository,
        advertisements,
        queue,
        now=clock,
        identifier=_identifier("M8"),
    )
    result_repository = InMemoryResultRepository()
    results = ResultService(result_repository, reviews)
    support_repository = InMemorySupportRepository()
    support = SupportService(
        support_repository,
        audit_sink=repository.add_audit_event,
        reviews=reviews,
        advertisements=advertisements,
        now=clock,
    )
    validation_repository = InMemoryValidationRepository()
    validation = ValidationService(
        validation_repository,
        reviews=reviews,
        results=results,
        now=clock,
        identifier=_identifier("M8"),
        audit_sink=repository.add_audit_event,
    )
    tokens = TokenService(JWT_SECRET, now=clock)
    services = ApplicationServices(
        repository=repository,
        auth=AuthService(
            repository,
            tokens,
            now=clock,
            rate_limiter=LoginRateLimiter(clock),
        ),
        advertisements=advertisements,
        standards=standards,
        reviews=reviews,
        results=results,
        support=support,
        validation=validation,
    )
    app = create_app(
        Settings(
            app_env="test",
            jwt_secret=SecretStr(JWT_SECRET),
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        ),
        services,
    )
    return M8Harness(
        TestClient(app),
        fixture,
        clock,
        repository,
        standards,
        review_repository,
        result_repository,
        queue,
        support_repository,
        validation_repository,
    )


def _headers(client: TestClient, email: str, request_id: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"x-request-id": f"{request_id}-login"},
    )
    assert response.status_code == 200, response.text
    return {
        "Authorization": f"Bearer {response.json()['accessToken']}",
        "x-request-id": request_id,
    }


def _create_advertisement(harness: M8Harness, headers: dict[str, str]) -> dict[str, Any]:
    fixture = harness.fixture["advertisement"]
    response = harness.client.post(
        "/api/v1/advertisements",
        headers=headers,
        data={
            "advertisementName": fixture["name"],
            "productGroup": fixture["productGroup"],
            "advertisementType": fixture["advertisementType"],
            "departmentId": fixture["departmentId"],
        },
        files={"advertisementFile": ("synthetic.png", PNG, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _request_review(
    harness: M8Harness, advertisement_id: str, headers: dict[str, str]
) -> dict[str, Any]:
    response = harness.client.post(
        f"/api/v1/advertisements/{advertisement_id}/reviews",
        headers=headers,
        json={"includeSuggestion": True, "includeOpinionDraft": True},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _complete_review(
    harness: M8Harness,
    review_id: str,
    *,
    standard_version_id: str,
    risk_level: str = "HIGH",
) -> None:
    bundle = harness.reviews.get(review_id)
    assert bundle is not None
    bundle.review.status = "REVIEW_COMPLETED"
    bundle.review.completed_at = harness.clock.value + timedelta(seconds=30)
    bundle.review.overall_risk_level = risk_level
    bundle.review.standard_version_ids = (standard_version_id,)
    bundle.job.status = "COMPLETED"
    bundle.job.progress_rate = 100
    bundle.job.current_step = "RESULT_PERSIST"
    for step in bundle.steps:
        step.status = "COMPLETED"


def _add_result(
    harness: M8Harness,
    review_id: str,
    file_id: str,
    standard_version_id: str,
    *,
    suffix: str = "0001",
) -> None:
    fixture = harness.fixture["advertisement"]
    evidence = ResultEvidence(
        f"EVD-M8-{suffix}",
        f"ECH-M8-{suffix}",
        standard_version_id,
        "INTERNAL_STANDARD",
        harness.fixture["standard"]["title"],
        None,
        "객관적 근거 없는 최고 표현을 금지한다.",
        1,
        0.91,
        "HYBRID",
    )
    item_id = f"ITEM-M8-{suffix}"
    annotation = ResultAnnotation(
        f"ANN-M8-{suffix}",
        item_id,
        file_id,
        "ADVERTISEMENT",
        "MISLEADING_EXPRESSION",
        "HIGH",
        fixture["targetText"],
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
        matched_text=fixture["targetText"],
    )
    harness.results.add(
        ResultItem(
            item_id,
            review_id,
            "MISLEADING_EXPRESSION",
            fixture["targetText"],
            "NEEDS_REVISION",
            "HIGH",
            "risk-policy-v1",
            ("MISLEADING_ABSOLUTE_EXPRESSION",),
            {
                "rule": {"matched": True, "ruleIds": ["RULE-M8-001"], "severity": "HIGH"},
                "rag": {
                    "topRelevanceScore": 0.91,
                    "evidenceCount": 1,
                    "evidenceSufficient": True,
                    "status": "CONNECTED",
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
            },
            "CONNECTED",
            None,
            "객관적 조건이 없는 최상급 표현입니다.",
            fixture["suggestedText"],
            "RULE",
            "provider-free-rule-v1",
            1,
            (evidence,),
            annotation,
        )
    )


def _seed_suggestion(harness: M8Harness, review_id: str, suffix: str = "0001") -> str:
    suggestion_id = f"SUG-M8-{suffix}"
    fixture = harness.fixture["advertisement"]
    harness.support.suggestions[suggestion_id] = {
        "suggestionId": suggestion_id,
        "reviewId": review_id,
        "reviewItemId": f"ITEM-M8-{suffix}",
        "originalText": fixture["targetText"],
        "suggestedText": fixture["suggestedText"],
        "suggestionReason": "확정 표현을 조건부 표현으로 완화",
        "evidenceIds": [f"EVD-M8-{suffix}"],
        "decisionStatus": "PENDING",
    }
    return suggestion_id


def _metric_projection(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in metric.items() if key != "metricName"}
        for metric in body["metrics"]
    ]


def test_e2e_001_advertisement_review_result_suggestion_and_report(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with harness.client:
        product = _headers(harness.client, "product@example.test", "m8-e2e-001-product")
        reviewer = _headers(harness.client, "reviewer@example.test", "m8-e2e-001-reviewer")
        advertisement = _create_advertisement(harness, product)
        review = _request_review(harness, advertisement["advertisementId"], product)

        status = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/status", headers=product
        )
        assert status.status_code == 200
        assert status.json()["jobStatus"] == "PENDING"
        assert harness.queue.messages == [
            {
                "messageVersion": "review-job-v1",
                "jobId": review["jobId"],
                "reviewId": review["reviewId"],
                "jobType": "REVIEW_ANALYSIS",
                "correlationId": "m8-e2e-001-product",
                "idempotencyKey": review["jobId"],
            }
        ]

        standard_version_id = "STDVER-M8-0001"
        _complete_review(harness, review["reviewId"], standard_version_id=standard_version_id)
        file_id = advertisement["files"][0]["fileId"]
        _add_result(harness, review["reviewId"], file_id, standard_version_id)
        suggestion_id = _seed_suggestion(harness, review["reviewId"])

        summary = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/summary", headers=product
        )
        items = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/items", headers=product
        )
        detail = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/items/ITEM-M8-0001", headers=product
        )
        annotations = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/annotations", headers=product
        )
        suggestions = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/suggestions", headers=product
        )
        assert summary.status_code == items.status_code == detail.status_code == 200
        assert annotations.status_code == suggestions.status_code == 200
        assert summary.json()["overallRiskLevel"] == "HIGH"
        assert summary.json()["standardVersionIds"] == [standard_version_id]
        assert items.json()["totalElements"] == 1
        assert detail.json()["evidences"][0]["matchSource"] == "HYBRID"
        assert annotations.json()["annotations"][0]["annotationDisplayMode"] == "BOX"
        assert suggestions.json()[0]["suggestionId"] == suggestion_id

        decision = harness.client.patch(
            f"/api/v1/suggestions/{suggestion_id}/decision",
            headers=reviewer,
            json={"decisionStatus": "ACCEPTED"},
        )
        report = harness.client.post(
            f"/api/v1/reviews/{review['reviewId']}/reports",
            headers=reviewer,
            json={"format": "PDF", "includeAnnotations": True, "includeSuggestions": True},
        )
        assert decision.status_code == report.status_code == 200
        assert report.json()["sourceReportId"] is not None
        download = harness.client.get(report.json()["downloadUrl"], headers=reviewer)
        assert download.status_code == 200
        assert f"sha256:{hashlib.sha256(download.content).hexdigest()}" == report.json()[
            "snapshotHash"
        ]
        actions = {event.action_type for event in harness.repository.list_audit_events()}
        assert {
            "ADVERTISEMENT_CREATE",
            "SUGGESTION_DECISION_CREATE",
            "REPORT_CREATE",
            "REPORT_DOWNLOADED",
        } <= actions


def test_e2e_002_standard_reindex_hybrid_evidence_and_version_trace(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with harness.client:
        manager = _headers(harness.client, "standard@example.test", "m8-e2e-002-standard")
        standard_fixture = harness.fixture["standard"]
        created = harness.client.post(
            "/api/v1/standards",
            headers=manager,
            files={
                "title": (None, standard_fixture["title"]),
                "evidenceType": (None, "INTERNAL_STANDARD"),
                "productGroup": (None, "SAVINGS"),
                "advertisementType": (None, "MOBILE_BANNER"),
                "ruleType": (None, "PROHIBITED"),
                "importance": (None, "HIGH"),
                "effectiveDate": (None, "2026-01-01"),
                "metadata": (
                    None,
                    json.dumps(standard_fixture["metadata"], ensure_ascii=False),
                ),
                "content": (None, standard_fixture["content"]),
            },
        )
        assert created.status_code == 201, created.text
        standard = created.json()
        reindex = harness.client.post(
            f"/api/v1/standards/{standard['standardId']}/versions/"
            f"{standard['standardVersionId']}/reindex",
            headers=manager,
            json=standard_fixture["reindex"],
        )
        assert reindex.status_code == 202, reindex.text
        assert reindex.json()["jobStatus"] == "SUCCEEDED"
        job = harness.client.get(
            f"/api/v1/standard-reindex-jobs/{reindex.json()['jobId']}", headers=manager
        )
        chunks = harness.client.get(
            f"/api/v1/evidences/{standard['evidenceId']}/chunks", headers=manager
        )
        search = harness.client.get(
            "/api/v1/evidences/search",
            headers=manager,
            params={"keyword": "최고 표현", "searchMode": "HYBRID"},
        )
        assert job.status_code == chunks.status_code == search.status_code == 200
        assert job.json()["embeddingModel"] == "fixed-fixture-v1"
        assert chunks.json()["totalElements"] == 2
        assert {
            (item["standardVersionId"], item["embeddingModel"], item["searchSchemaVersion"])
            for item in chunks.json()["contents"]
        } == {(standard["standardVersionId"], "fixed-fixture-v1", "search-schema-v1")}
        assert search.json()[0]["standardVersionId"] == standard["standardVersionId"]
        assert search.json()[0]["matchSource"] == "HYBRID"

        product = _headers(harness.client, "product@example.test", "m8-e2e-002-product")
        advertisement = _create_advertisement(harness, product)
        review = _request_review(harness, advertisement["advertisementId"], product)
        _complete_review(
            harness,
            review["reviewId"],
            standard_version_id=standard["standardVersionId"],
        )
        _add_result(
            harness,
            review["reviewId"],
            advertisement["files"][0]["fileId"],
            standard["standardVersionId"],
        )
        detail = harness.client.get(
            f"/api/v1/reviews/{review['reviewId']}/items/ITEM-M8-0001", headers=product
        )
        assert detail.status_code == 200
        assert detail.json()["evidences"][0]["standardVersionId"] == standard[
            "standardVersionId"
        ]
        assert detail.json()["evidences"][0]["matchSource"] == "HYBRID"


def test_e2e_003_revision_comparison_rerun_and_independent_history(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with harness.client:
        product = _headers(harness.client, "product@example.test", "m8-e2e-003-product")
        reviewer = _headers(harness.client, "reviewer@example.test", "m8-e2e-003-reviewer")
        advertisement = _create_advertisement(harness, product)
        first = _request_review(harness, advertisement["advertisementId"], product)
        _complete_review(harness, first["reviewId"], standard_version_id="STDVER-M8-0001")
        _add_result(
            harness,
            first["reviewId"],
            advertisement["files"][0]["fileId"],
            "STDVER-M8-0001",
        )
        _seed_suggestion(harness, first["reviewId"])
        first_report = harness.client.post(
            f"/api/v1/reviews/{first['reviewId']}/reports",
            headers=reviewer,
            json={"format": "HWPX", "includeSuggestions": True},
        )
        assert first_report.status_code == 200
        first_download = harness.client.get(first_report.json()["downloadUrl"], headers=reviewer)

        revision = harness.client.post(
            f"/api/v1/advertisements/{advertisement['advertisementId']}/revisions",
            headers=product,
            data={"revisionMemo": "replace absolute claim with conditional language"},
            files={
                "revisedAdvertisementFile": (
                    "synthetic-revision.png",
                    PNG + b"m8-revision",
                    "image/png",
                )
            },
        )
        assert revision.status_code == 201, revision.text
        comparison = harness.client.post(
            f"/api/v1/advertisements/{advertisement['advertisementId']}/comparisons",
            headers=product,
            json={
                "baseReviewId": first["reviewId"],
                "revisionId": revision.json()["revisionId"],
            },
        )
        assert comparison.status_code == 200, comparison.text
        assert {
            item["resolutionStatus"] for item in comparison.json()["items"]
        } == {"RESOLVED", "UNRESOLVED", "NEW_ISSUE"}

        rerun = harness.client.post(
            f"/api/v1/reviews/{first['reviewId']}/rerun",
            headers=product,
            json={"reason": "verify the registered revision"},
        )
        assert rerun.status_code == 202, rerun.text
        second_id = rerun.json()["newReviewId"]
        assert second_id != first["reviewId"]
        assert rerun.json()["previousReviewId"] == first["reviewId"]
        assert harness.queue.messages[-1]["jobType"] == "RE_REVIEW"
        _complete_review(harness, second_id, standard_version_id="STDVER-M8-0001", risk_level="LOW")
        _add_result(
            harness,
            second_id,
            advertisement["files"][0]["fileId"],
            "STDVER-M8-0001",
            suffix="0002",
        )
        _seed_suggestion(harness, second_id, "0002")
        second_report = harness.client.post(
            f"/api/v1/reviews/{second_id}/reports",
            headers=reviewer,
            json={"format": "HWPX", "includeSuggestions": True},
        )
        assert second_report.status_code == 200
        assert second_report.json()["snapshotHash"] != first_report.json()["snapshotHash"]

        unchanged = harness.client.get(first_report.json()["downloadUrl"], headers=reviewer)
        assert unchanged.content == first_download.content
        assert f"sha256:{hashlib.sha256(unchanged.content).hexdigest()}" == first_report.json()[
            "snapshotHash"
        ]
        history = harness.client.get(
            f"/api/v1/advertisements/{advertisement['advertisementId']}/reviews",
            headers=product,
        )
        assert [item["reviewRound"] for item in history.json()] == [2, 1]
        assert harness.client.get(
            f"/api/v1/comparisons/{comparison.json()['comparisonId']}", headers=product
        ).json() == comparison.json()


def test_e2e_004_validation_judgment_snapshot_hash_and_kpi(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with harness.client:
        reviewer = _headers(harness.client, "reviewer@example.test", "m8-e2e-004-reviewer")
        validation = harness.fixture["validation"]
        dataset_response = harness.client.post(
            "/api/v1/validation/datasets",
            headers=reviewer,
            data={
                "datasetName": "Synthetic M8 release dataset",
                "productGroup": "SAVINGS",
                "advertisementType": "MOBILE_BANNER",
                "labelJson": json.dumps({"cases": validation["cases"]}),
                "excluded": "false",
            },
            files={"advertisementFile": ("synthetic-validation.png", PNG, "image/png")},
        )
        assert dataset_response.status_code == 201, dataset_response.text
        dataset = dataset_response.json()
        assert dataset["labelJson"]["_artifacts"]["advertisement"]["sha256"]
        judgments = harness.client.post(
            f"/api/v1/validation/datasets/{dataset['datasetId']}/judgments",
            headers=reviewer,
            json={"judgments": validation["judgments"]},
        )
        assert judgments.status_code == 201, judgments.text
        request = {
            "datasetIds": [dataset["datasetId"]],
            "metrics": [
                "REQUIRED_PHRASE_ACCURACY",
                "MISLEADING_EXPRESSION_ACCURACY",
                "EVIDENCE_PRECISION",
                "HUMAN_AGREEMENT_RATE",
            ],
            "excludeInvalidSamples": True,
            "reviewSelectionPolicy": "LATEST_COMPLETED",
        }
        first = harness.client.post(
            "/api/v1/validation/evaluations", headers=reviewer, json=request
        )
        repeat = harness.client.post(
            "/api/v1/validation/evaluations", headers=reviewer, json=request
        )
        assert first.status_code == repeat.status_code == 201
        assert first.json()["evaluationId"] != repeat.json()["evaluationId"]
        assert first.json()["snapshotHash"] == repeat.json()["snapshotHash"]
        assert first.json()["snapshotHash"].startswith("sha256:")
        assert first.json()["versionSnapshot"]["modelVersion"] == "provider-free-runtime-v1"
        assert first.json()["exclusionSummary"] == validation["expectedExclusionSummary"]
        assert _metric_projection(first.json()) == validation["expectedMetrics"]

        original = harness.client.get(
            f"/api/v1/validation/evaluations/{first.json()['evaluationId']}", headers=reviewer
        )
        assert original.json() == first.json()
        changed_judgments = harness.client.post(
            f"/api/v1/validation/datasets/{dataset['datasetId']}/judgments",
            headers=reviewer,
            json={
                "judgments": [
                    {
                        **validation["judgments"][0],
                        "comment": "synthetic golden judgment version two",
                    }
                ]
            },
        )
        assert changed_judgments.status_code == 201
        assert changed_judgments.json()["judgments"][0]["judgmentVersion"] == 2
        changed = harness.client.post(
            "/api/v1/validation/evaluations", headers=reviewer, json=request
        )
        assert changed.status_code == 201
        assert changed.json()["snapshotHash"] != first.json()["snapshotHash"]
        assert harness.client.get(
            f"/api/v1/validation/evaluations/{first.json()['evaluationId']}", headers=reviewer
        ).json() == first.json()
        actions = {event.action_type for event in harness.repository.list_audit_events()}
        assert {
            "VALIDATION_DATASET_CREATE",
            "VALIDATION_JUDGMENT_CREATE",
            "VALIDATION_EVALUATION_CREATE",
            "VALIDATION_EVALUATION_READ",
        } <= actions
        assert harness.fixture["containsCustomerData"] is False
        assert harness.fixture["networkAllowed"] is False
        assert harness.fixture["provider"] is None
