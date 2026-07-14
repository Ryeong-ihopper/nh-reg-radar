import base64
import zlib
from io import BytesIO

from fastapi.testclient import TestClient
from httpx import Response

from conftest import login
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.storage import MAX_FILE_SIZE, UploadValidationError, validate_upload


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def png_with_payload(payload_size: int) -> bytes:
    signature_and_ihdr = PNG[:33]
    payload = b"x" * payload_size
    chunk = len(payload).to_bytes(4, "big") + b"tEXt" + payload
    chunk += (zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF).to_bytes(4, "big")
    return signature_and_ihdr + chunk + PNG[-12:]


def upload(
    client: TestClient,
    token: str,
    department_id: str = "DPT-A",
    body: bytes = PNG,
) -> Response:
    return client.post(
        "/api/v1/advertisements",
        headers={"Authorization": f"Bearer {token}", "x-request-id": "req-upload"},
        data={
            "advertisementName": "안전한 배너",
            "productGroup": "SAVINGS",
            "advertisementType": "MOBILE_BANNER",
            "departmentId": department_id,
        },
        files={"advertisementFile": ("banner.png", body, "image/png")},
    )


def test_upload_list_detail_preview_download_and_scope(
    client: TestClient,
    repository: InMemoryRepository,
) -> None:
    token_a, _ = login(client, "a@example.com")
    created = upload(client, token_a)
    assert created.status_code == 201, created.text
    payload = created.json()
    assert "object" not in created.text.casefold() and "storage" not in created.text.casefold()
    advertisement_id = payload["advertisementId"]
    file_id = payload["files"][0]["fileId"]

    listing = client.get("/api/v1/advertisements", headers={"Authorization": f"Bearer {token_a}"})
    assert listing.status_code == 200
    assert [item["advertisementId"] for item in listing.json()["contents"]] == [advertisement_id]
    detail = client.get(
        f"/api/v1/advertisements/{advertisement_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert detail.status_code == 200

    preview = client.get(
        f"/api/v1/files/{file_id}/preview",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert preview.status_code == 200
    assert preview.json()["previewPath"].endswith("/preview/content")
    content = client.get(
        f"{preview.json()['previewPath']}?pageNo={preview.json()['pageNo']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert content.status_code == 200 and content.content == PNG
    download = client.get(
        f"/api/v1/files/{file_id}/download",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert download.status_code == 200 and download.content == PNG

    token_b, _ = login(client, "b@example.com")
    hidden = client.get("/api/v1/advertisements", headers={"Authorization": f"Bearer {token_b}"})
    assert hidden.json()["totalElements"] == 0
    assert (
        client.get(
            f"/api/v1/advertisements/{advertisement_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/files/{file_id}/download",
            headers={"Authorization": f"Bearer {token_b}"},
        ).status_code
        == 403
    )
    assert any(
        event.result == "DENIED" and event.trace_id != "" for event in repository.audit_events
    )
    assert {event.action_type for event in repository.audit_events} >= {
        "ADVERTISEMENT_CREATE",
        "FILE_PREVIEW",
        "FILE_DOWNLOAD",
    }
    assert all(
        "object" not in json_value
        for event in repository.audit_events
        for json_value in event.metadata.values()
    )


def test_file_error_statuses_and_duplicates(client: TestClient) -> None:
    token, _ = login(client)
    unsupported = client.post(
        "/api/v1/advertisements",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "advertisementName": "x",
            "productGroup": "SAVINGS",
            "advertisementType": "NOTICE",
            "departmentId": "DPT-A",
        },
        files={"advertisementFile": ("bad.exe", b"MZ", "application/octet-stream")},
    )
    assert unsupported.status_code == 415
    corrupt = upload(client, token, body=b"not-a-png")
    assert corrupt.status_code == 400 and corrupt.json()["code"] == "FILE_READ_FAILED"
    assert upload(client, token).status_code == 201
    duplicate = upload(client, token)
    assert duplicate.status_code == 409

    duplicate_request = client.post(
        "/api/v1/advertisements",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "advertisementName": "dup",
            "productGroup": "SAVINGS",
            "advertisementType": "NOTICE",
            "departmentId": "DPT-A",
        },
        files=[
            ("advertisementFile", ("one.png", PNG, "image/png")),
            ("additionalFiles", ("two.png", PNG, "image/png")),
        ],
    )
    assert duplicate_request.status_code == 409


def test_size_boundary_and_filename_normalization() -> None:
    exact = png_with_payload(MAX_FILE_SIZE - 57)
    validated = validate_upload("../safe.png", "image/png", BytesIO(exact))
    assert validated.size == MAX_FILE_SIZE and validated.original_file_name == "safe.png"
    too_large = exact + b"x"
    try:
        validate_upload("large.png", "image/png", BytesIO(too_large))
    except UploadValidationError as exc:
        assert exc.code == "FILE_SIZE_EXCEEDED"
    else:
        raise AssertionError("oversized upload was accepted")
    try:
        validate_upload("header-only.png", "image/png", BytesIO(b"\x89PNG\r\n\x1a\n"))
    except UploadValidationError as exc:
        assert exc.code == "FILE_READ_FAILED"
    else:
        raise AssertionError("header-only PNG was accepted")


def test_admin_audit_contract_and_denial(client: TestClient) -> None:
    standard, _ = login(client, "standard@example.com")
    denied = client.get(
        "/api/v1/admin/audit-logs",
        headers={"Authorization": f"Bearer {standard}", "x-request-id": "req-audit-denied"},
    )
    assert denied.status_code == 403
    admin, _ = login(client, "admin@example.com")
    logs = client.get(
        "/api/v1/admin/audit-logs?actionType=AUDIT_LOG_READ",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert logs.status_code == 200
    assert logs.json()["contents"][0]["traceId"] == "req-audit-denied"
