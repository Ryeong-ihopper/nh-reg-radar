import base64
import zlib
from io import BytesIO

from fastapi.testclient import TestClient
from httpx import Response

from conftest import PdfPreviewRenderer, login
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.storage import MAX_FILE_SIZE, UploadValidationError, validate_upload


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


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


def test_system_admin_can_delete_advertisement_and_hide_its_files(
    client: TestClient,
    repository: InMemoryRepository,
) -> None:
    owner, _ = login(client, "a@example.com")
    created = upload(client, owner)
    assert created.status_code == 201, created.text
    advertisement_id = created.json()["advertisementId"]
    file_id = created.json()["files"][0]["fileId"]

    denied = client.delete(
        f"/api/v1/advertisements/{advertisement_id}",
        headers={"Authorization": f"Bearer {owner}", "x-request-id": "req-delete-denied"},
    )
    assert denied.status_code == 403

    admin, _ = login(client, "admin@example.com")
    deleted = client.delete(
        f"/api/v1/advertisements/{advertisement_id}",
        headers={"Authorization": f"Bearer {admin}", "x-request-id": "req-delete-admin"},
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/advertisements/{advertisement_id}",
            headers={"Authorization": f"Bearer {admin}"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/files/{file_id}/download",
            headers={"Authorization": f"Bearer {admin}"},
        ).status_code
        == 404
    )
    listing = client.get("/api/v1/advertisements", headers={"Authorization": f"Bearer {admin}"})
    assert advertisement_id not in [item["advertisementId"] for item in listing.json()["contents"]]
    assert any(
        event.action_type == "ADVERTISEMENT_DELETE"
        and event.result == "SUCCESS"
        and event.trace_id == "req-delete-admin"
        for event in repository.audit_events
    )


def test_loan_is_an_available_product_group_for_registration(client: TestClient) -> None:
    token, _ = login(client, "a@example.com")

    created = client.post(
        "/api/v1/advertisements",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "advertisementName": "대출 상품 안내",
            "productGroup": "LOAN",
            "advertisementType": "NOTICE",
            "departmentId": "DPT-A",
        },
        files={"advertisementFile": ("loan.png", PNG, "image/png")},
    )

    assert created.status_code == 201, created.text
    detail = client.get(
        f"/api/v1/advertisements/{created.json()['advertisementId']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.json()["productGroup"] == "LOAN"
    codes = client.get("/api/v1/codes/product-groups", headers={"Authorization": f"Bearer {token}"})
    assert any(item["code"] == "LOAN" for item in codes.json())


def test_preview_renders_pdf_to_the_same_raster_coordinate_basis_as_ocr(
    services,
    client: TestClient,
) -> None:
    token, _ = login(client)
    created = client.post(
        "/api/v1/advertisements",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "advertisementName": "PDF 미리보기",
            "productGroup": "SAVINGS",
            "advertisementType": "MOBILE_BANNER",
            "departmentId": "DPT-A",
        },
        files={"advertisementFile": ("banner.pdf", PDF, "application/pdf")},
    )
    assert created.status_code == 201, created.text
    file_id = created.json()["files"][0]["fileId"]

    descriptor = client.get(
        f"/api/v1/files/{file_id}/preview?pageNo=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert descriptor.status_code == 200
    assert descriptor.json()["totalPages"] == 2
    renderer = services.pdf_preview
    assert isinstance(renderer, PdfPreviewRenderer)
    assert renderer.describe_calls == 1
    assert renderer.render_calls == 0
    content = client.get(
        f"/api/v1/files/{file_id}/preview/content?pageNo=1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert renderer.render_calls == 1


def test_hwp_preview_is_converted_by_the_private_renderer(client: TestClient) -> None:
    token, _ = login(client)
    hwp = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1preview"
    created = client.post(
        "/api/v1/advertisements",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "advertisementName": "HWP 미리보기",
            "productGroup": "SAVINGS",
            "advertisementType": "MOBILE_BANNER",
            "departmentId": "DPT-A",
        },
        files={"advertisementFile": ("banner.hwp", hwp, "application/x-hwp")},
    )
    assert created.status_code == 201, created.text
    file_id = created.json()["files"][0]["fileId"]

    descriptor = client.get(
        f"/api/v1/files/{file_id}/preview?pageNo=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert descriptor.status_code == 200
    assert descriptor.json()["totalPages"] == 2
    content = client.get(
        f"/api/v1/files/{file_id}/preview/content?pageNo=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in content.content
    assert "sandbox" in content.headers["content-security-policy"]


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


def test_create_rejects_unknown_product_group_and_advertisement_type(
    client: TestClient,
    repository: InMemoryRepository,
) -> None:
    token, _ = login(client)
    for field, value in (
        ("productGroup", "UNKNOWN_PRODUCT"),
        ("advertisementType", "UNKNOWN_TYPE"),
    ):
        data = {
            "advertisementName": "invalid enum",
            "productGroup": "SAVINGS",
            "advertisementType": "NOTICE",
            "departmentId": "DPT-A",
        }
        data[field] = value
        response = client.post(
            "/api/v1/advertisements",
            headers={"Authorization": f"Bearer {token}"},
            data=data,
            files={"advertisementFile": ("banner.png", PNG, "image/png")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "BAD_REQUEST"
    assert repository.advertisements == {}


def test_all_persisted_review_statuses_remain_readable(
    client: TestClient,
    repository: InMemoryRepository,
) -> None:
    token, _ = login(client)
    advertisement_id = upload(client, token).json()["advertisementId"]
    advertisement = repository.get_advertisement(advertisement_id)
    assert advertisement is not None

    for status in (
        "UPLOADED",
        "ANALYSIS_REQUESTED",
        "ANALYZING",
        "CHECK_REQUIRED",
        "REVIEW_COMPLETED",
        "REVIEW_FAILED",
        "REVISED",
    ):
        advertisement.review_status = status
        listing = client.get("/api/v1/advertisements", headers={"Authorization": f"Bearer {token}"})
        detail = client.get(
            f"/api/v1/advertisements/{advertisement_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert listing.status_code == 200, (status, listing.text)
        assert detail.status_code == 200, (status, detail.text)
        assert listing.json()["contents"][0]["reviewStatus"] == status
        assert detail.json()["reviewStatus"] == status


def test_revision_registration_stores_revision_file_and_preserves_scope_and_audit(
    client: TestClient,
    repository: InMemoryRepository,
) -> None:
    token_a, _ = login(client, "a@example.com")
    advertisement_id = upload(client, token_a).json()["advertisementId"]

    revised = client.post(
        f"/api/v1/advertisements/{advertisement_id}/revisions",
        headers={"Authorization": f"Bearer {token_a}", "x-request-id": "req-revision"},
        data={"revisionMemo": "확정 표현 완화"},
        files={
            "revisedAdvertisementFile": (
                "revised.png",
                png_with_payload(1),
                "image/png",
            )
        },
    )

    assert revised.status_code == 201, revised.text
    assert revised.json() == {
        "advertisementId": advertisement_id,
        "revisionId": "REVISION-0003",
        "reviewStatus": "REVISED",
    }
    revision = repository.get_revision(revised.json()["revisionId"])
    assert revision is not None
    assert revision.revision_no == 1
    assert revision.revision_memo == "확정 표현 완화"
    assert revision.file.revision_id == revision.revision_id
    assert repository.get_advertisement(advertisement_id).review_status == "REVISED"  # type: ignore[union-attr]
    assert any(
        event.action_type == "ADVERTISEMENT_REVISION_CREATE"
        and event.target_id == revised.json()["revisionId"]
        and event.trace_id == "req-revision"
        for event in repository.audit_events
    )

    token_b, _ = login(client, "b@example.com")
    denied = client.post(
        f"/api/v1/advertisements/{advertisement_id}/revisions",
        headers={"Authorization": f"Bearer {token_b}", "x-request-id": "req-revision-denied"},
        files={"revisedAdvertisementFile": ("denied.png", png_with_payload(2), "image/png")},
    )
    assert denied.status_code == 403
    assert any(
        event.action_type == "ADVERTISEMENT_REVISION_CREATE"
        and event.result == "DENIED"
        and event.trace_id == "req-revision-denied"
        for event in repository.audit_events
    )


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
