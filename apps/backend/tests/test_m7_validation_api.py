"""End-to-end provider-free tests for the five M7 Validation operations."""

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import JWT_SECRET, Clock, login
from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.settings import Settings
from nh_ad_backend.validation import InMemoryValidationRepository, ValidationService


FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "m7" / "validation-kpi-v1.json"


def validation_client(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> tuple[TestClient, InMemoryValidationRepository]:
    counters: defaultdict[str, int] = defaultdict(int)

    def identifier(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}-M7-{counters[prefix]:04d}"

    validation_repository = InMemoryValidationRepository()
    validation = ValidationService(
        validation_repository,
        now=clock,
        identifier=identifier,
        audit_sink=repository.add_audit_event,
    )
    app = create_app(
        Settings(
            app_env="test",
            jwt_secret=JWT_SECRET,
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        ),
        replace(services, validation=validation),
    )
    return TestClient(app), validation_repository


def create_dataset(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    response = client.post(
        "/api/v1/validation/datasets",
        headers=headers,
        data={
            "datasetName": "Synthetic M7",
            "productGroup": "SAVINGS",
            "advertisementType": "MOBILE_BANNER",
            "labelJson": json.dumps({"cases": fixture["cases"]}),
            "excluded": "false",
        },
        files={"advertisementFile": ("synthetic.png", b"synthetic-m7", "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_m7_routes_enforce_role_scope_and_store_exact_kpis(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    client, _ = validation_client(services, repository, clock)
    with client:
        product_token, _ = login(client)
        product_headers = {"Authorization": f"Bearer {product_token}"}
        denied = client.post(
            "/api/v1/validation/datasets",
            headers=product_headers,
            data={
                "datasetName": "Denied",
                "productGroup": "SAVINGS",
                "advertisementType": "MOBILE_BANNER",
            },
            files={"advertisementFile": ("synthetic.png", b"fixture", "image/png")},
        )
        assert denied.status_code == 403

        reviewer_token, _ = login(client, "review@example.com")
        headers = {"Authorization": f"Bearer {reviewer_token}"}
        dataset = create_dataset(client, headers)
        assert dataset["datasetId"] == "DATASET-M7-0001"
        assert dataset["datasetVersion"] == 1
        assert dataset["labelJson"]["_artifacts"]["advertisement"]["sha256"]

        listing = client.get("/api/v1/validation/datasets", headers=headers)
        assert listing.status_code == 200
        assert listing.json()["totalElements"] == 1

        judgments_payload = {
            "judgments": [
                {
                    "targetText": "Synthetic unsupported best claim",
                    "reviewType": "MISLEADING_EXPRESSION",
                    "expectedStatus": "NEEDS_REVISION",
                    "riskLevel": "HIGH",
                    "comment": "synthetic golden judgment",
                    "excluded": False,
                }
            ]
        }
        first = client.post(
            f"/api/v1/validation/datasets/{dataset['datasetId']}/judgments",
            headers=headers,
            json=judgments_payload,
        )
        second = client.post(
            f"/api/v1/validation/datasets/{dataset['datasetId']}/judgments",
            headers=headers,
            json=judgments_payload,
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["judgments"][0]["judgmentVersion"] == 1
        assert second.json()["judgments"][0]["judgmentVersion"] == 2

        evaluation = client.post(
            "/api/v1/validation/evaluations",
            headers=headers,
            json={
                "datasetIds": [dataset["datasetId"]],
                "metrics": [
                    "REQUIRED_PHRASE_ACCURACY",
                    "MISLEADING_EXPRESSION_ACCURACY",
                    "EVIDENCE_PRECISION",
                    "HUMAN_AGREEMENT_RATE",
                ],
                "excludeInvalidSamples": True,
                "reviewSelectionPolicy": "LATEST_COMPLETED",
            },
        )
        assert evaluation.status_code == 201, evaluation.text
        body = evaluation.json()
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert [
            {key: value for key, value in metric.items() if key != "metricName"}
            for metric in body["metrics"]
        ] == fixture["expectedMetrics"]
        assert body["exclusionSummary"] == fixture["expectedExclusionSummary"]
        assert body["snapshotHash"].startswith("sha256:")

        stored = client.get(
            f"/api/v1/validation/evaluations/{body['evaluationId']}", headers=headers
        )
        assert stored.status_code == 200
        assert stored.json() == body
        assert {event.action_type for event in repository.list_audit_events()} >= {
            "VALIDATION_DATASET_CREATE",
            "VALIDATION_DATASET_LIST",
            "VALIDATION_JUDGMENT_CREATE",
            "VALIDATION_EVALUATION_CREATE",
            "VALIDATION_EVALUATION_READ",
        }


def test_existing_evaluation_is_immutable_after_new_golden_judgment(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    client, _ = validation_client(services, repository, clock)
    with client:
        reviewer_token, _ = login(client, "review@example.com")
        headers = {"Authorization": f"Bearer {reviewer_token}"}
        dataset = create_dataset(client, headers)
        request = {
            "datasetIds": [dataset["datasetId"]],
            "metrics": list(
                (
                    "REQUIRED_PHRASE_ACCURACY",
                    "MISLEADING_EXPRESSION_ACCURACY",
                    "EVIDENCE_PRECISION",
                    "HUMAN_AGREEMENT_RATE",
                )
            ),
            "excludeInvalidSamples": True,
            "reviewSelectionPolicy": "LATEST_COMPLETED",
        }
        first = client.post("/api/v1/validation/evaluations", headers=headers, json=request).json()
        client.post(
            f"/api/v1/validation/datasets/{dataset['datasetId']}/judgments",
            headers=headers,
            json={
                "judgments": [
                    {
                        "targetText": "new golden label",
                        "reviewType": "REQUIRED_PHRASE",
                        "expectedStatus": "APPROPRIATE",
                    }
                ]
            },
        )
        unchanged = client.get(
            f"/api/v1/validation/evaluations/{first['evaluationId']}", headers=headers
        ).json()
        second = client.post("/api/v1/validation/evaluations", headers=headers, json=request).json()

        assert unchanged == first
        assert second["evaluationId"] != first["evaluationId"]
        assert second["snapshotHash"] != first["snapshotHash"]
        assert second["metrics"] == first["metrics"]
