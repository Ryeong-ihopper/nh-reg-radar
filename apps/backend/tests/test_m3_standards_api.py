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


def test_reindex_rejects_unknown_or_scope_inconsistent_target_indexes(
    client: TestClient,
) -> None:
    access_token, _ = login(client, "standard@example.com")
    created = client.post(
        "/api/v1/standards",
        headers={"authorization": f"Bearer {access_token}"},
        files={
            "title": (None, "재색인 대상 검증"),
            "evidenceType": (None, "INTERNAL_STANDARD"),
            "productGroup": (None, "SAVINGS"),
            "advertisementType": (None, "MOBILE_BANNER"),
            "ruleType": (None, "PROHIBITED"),
            "importance": (None, "HIGH"),
            "effectiveDate": (None, "2026-01-01"),
            "metadata": (
                None,
                json.dumps(
                    {
                        "owningDepartment": "준법부",
                        "documentName": "광고심의 내규",
                        "sectionPath": "표현/금지",
                        "effectiveDate": "2026-01-01",
                        "version": "1.0",
                        "productGroup": "SAVINGS",
                    },
                    ensure_ascii=False,
                ),
            ),
            "content": (None, "근거 없는 최고 표현을 금지한다."),
        },
    )
    assert created.status_code == 201, created.text
    path = (
        f"/api/v1/standards/{created.json()['standardId']}"
        f"/versions/{created.json()['standardVersionId']}/reindex"
    )
    base = {
        "reindexScope": "KEYWORD_ONLY",
        "reason": "target validation",
        "chunkingPolicyVersion": "reference-chunking-v1",
        "searchSchemaVersion": "search-schema-v1",
    }
    for targets in (["UNKNOWN"], ["QDRANT"]):
        response = client.post(
            path,
            headers={"authorization": f"Bearer {access_token}"},
            json={**base, "targetIndexes": targets},
        )
        assert response.status_code == 400, response.text

    accepted = client.post(
        path,
        headers={"authorization": f"Bearer {access_token}"},
        json={**base, "targetIndexes": ["OPENSEARCH"]},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["targetIndexes"] == ["OPENSEARCH"]

    subset = client.post(
        path,
        headers={"authorization": f"Bearer {access_token}"},
        json={
            **base,
            "reindexScope": "INDEX_ONLY",
            "targetIndexes": ["QDRANT"],
        },
    )
    assert subset.status_code == 202, subset.text
    assert subset.json()["targetIndexes"] == ["QDRANT"]
    assert subset.json()["qdrantStatus"] == "ACTIVE"
    assert subset.json()["opensearchStatus"] == "PENDING"
