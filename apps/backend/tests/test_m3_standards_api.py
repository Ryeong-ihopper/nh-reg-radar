import json

from fastapi.testclient import TestClient

from conftest import login


def test_create_standard_response_matches_frozen_camel_case_contract(
    client: TestClient,
) -> None:
    access_token, _ = login(client, "standard@example.com")
    metadata = {
        "owningDepartment": "준법부",
        "documentName": "광고심의 내규",
        "sectionPath": "표현/금지",
        "effectiveDate": "2026-01-01",
        "version": "1.0",
        "productGroup": "SAVINGS",
    }

    response = client.post(
        "/api/v1/standards",
        headers={
            "authorization": f"Bearer {access_token}",
            "x-request-id": "req-standard-create",
        },
        files={
            "title": (None, "광고심의 내규"),
            "evidenceType": (None, "INTERNAL_STANDARD"),
            "productGroup": (None, "SAVINGS"),
            "advertisementType": (None, "MOBILE_BANNER"),
            "ruleType": (None, "PROHIBITED"),
            "importance": (None, "HIGH"),
            "effectiveDate": (None, "2026-01-01"),
            "metadata": (None, json.dumps(metadata, ensure_ascii=False)),
            "content": (None, "객관적 근거 없는 최고 표현을 금지한다."),
        },
    )

    assert response.status_code == 201, response.text
    assert set(response.json()) == {
        "standardId",
        "evidenceId",
        "standardVersionId",
        "version",
        "isActive",
    }
    assert response.json()["version"] == "1.0"
    assert response.json()["isActive"] is True
