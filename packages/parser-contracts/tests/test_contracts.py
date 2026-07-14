import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from nh_ad_parser_contracts import (
    ArtifactAccessDenied,
    ArtifactChecksumMismatch,
    ArtifactStore,
    Coordinate,
    DocumentInput,
    InMemoryArtifactMetadataRepository,
    InMemoryArtifactStorage,
    NormalizedDocument,
    ParserRouter,
    confidence_status,
)

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "m4"


@pytest.mark.parametrize("name", ["normalized-image-v1.json", "normalized-hwpx-v1.json"])
def test_normalized_document_v1_round_trip_is_lossless(name: str) -> None:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    document = NormalizedDocument.model_validate(payload)

    assert document.model_dump(mode="json", by_alias=True) == payload


def test_coordinate_and_confidence_thresholds_are_contract_validated() -> None:
    assert [confidence_status(score).value for score in (0.80, 0.79, 0.49)] == [
        "READABLE",
        "LOW_CONFIDENCE",
        "UNREADABLE",
    ]
    with pytest.raises(ValidationError, match="normalized coordinates"):
        Coordinate.model_validate(
            {
                "sourceWidth": 100,
                "sourceHeight": 100,
                "sourceUnit": "px",
                "x": 10,
                "y": 10,
                "width": 20,
                "height": 20,
                "normalizedX": 0.2,
                "normalizedY": 0.1,
                "normalizedWidth": 0.2,
                "normalizedHeight": 0.2,
                "rotation": 0,
                "coordinateConfidence": 0.9,
            }
        )


def test_parser_router_selects_primary_engines_and_guards_vlm() -> None:
    router = ParserRouter()
    base = {
        "source_file_id": "FILE-1",
        "review_id": "REV-1",
        "mime_type": "application/octet-stream",
        "body": b"synthetic",
    }

    assert router.route(DocumentInput(file_name="a.hwpx", **base)).primary_adapter == "rhwp"
    assert (
        router.route(DocumentInput(file_name="a.pdf", scanned_pdf=True, **base)).primary_adapter
        == "paddleocr"
    )
    complex_pdf = router.route(DocumentInput(file_name="a.pdf", complex_layout=True, **base))
    assert complex_pdf.primary_adapter == "opendataloader-pdf"
    assert complex_pdf.quality_rerun_reason == "TABLE_EXTRACTION_MISSING"
    image = router.route(DocumentInput(file_name="a.png", **base))
    assert image.primary_adapter == "paddleocr"
    assert image.secondary_adapters == ()
    approved_image = router.route(
        DocumentInput(file_name="a.png", external_ai_allowed=True, **base)
    )
    assert approved_image.secondary_adapters == ("vlm-ocr",)


def test_raw_artifact_checksum_access_retention_and_audit_are_enforced() -> None:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    storage = InMemoryArtifactStorage()
    repository = InMemoryArtifactMetadataRepository()
    audit: list[dict[str, str]] = []
    store = ArtifactStore(storage, repository, bucket="test-parser-artifacts", audit=audit.append)
    body = (FIXTURES / "raw-provider-v1.json").read_bytes()
    metadata = store.put(
        body,
        raw_artifact_id="RAWART-1",
        review_id="REV-1",
        file_id="FILE-1",
        review_step_id="STEP-1",
        artifact_type="OCR_RAW",
        content_type="application/json",
        parser_name="paddleocr",
        parser_version="fixture-1",
        parser_rule_version="rules-v1",
        ir_version="normalized-document-v1",
        attempt_no=1,
        is_primary_attempt=True,
        is_selected_output=True,
        rerun_reason_code=None,
        confidence_score=0.94,
        confidence_status="READABLE",
        created_at=now,
        retention_until=now + timedelta(days=7),
    )

    assert metadata.checksum_sha256
    assert "RAWART-1" not in metadata.object_key
    with pytest.raises(ArtifactAccessDenied):
        store.read_privileged(
            "RAWART-1", role="PRODUCT_DEPARTMENT_USER", actor_id="user", purpose="view"
        )
    assert (
        store.read_privileged("RAWART-1", role="SYSTEM_ADMIN", actor_id="admin", purpose="incident")
        == body
    )
    assert all("objectKey" not in event and "url" not in event for event in audit)
    assert not store.delete_expired(
        "RAWART-1", now=now + timedelta(days=8), approved=False, actor_id="admin"
    )

    storage.objects[(metadata.bucket, metadata.object_key)] = b"tampered"
    with pytest.raises(ArtifactChecksumMismatch):
        store.read_privileged("RAWART-1", role="SYSTEM_ADMIN", actor_id="admin", purpose="incident")
    storage.objects[(metadata.bucket, metadata.object_key)] = body
    assert store.delete_expired(
        "RAWART-1", now=now + timedelta(days=8), approved=True, actor_id="admin"
    )
