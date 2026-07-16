from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from nh_ad_parser_contracts import DocumentInput

from nh_ad_worker.parser_services import ParserServiceAdapter, ParserServiceError


def _document() -> DocumentInput:
    return DocumentInput(
        source_file_id="FILE-1",
        review_id="REV-1",
        file_name="sample.pdf",
        mime_type="application/pdf",
        body=b"%PDF-sample",
    )


def _normalized(parser_name: str) -> dict[str, object]:
    return {
        "documentId": "doc-FILE-1",
        "sourceFileId": "FILE-1",
        "reviewId": "REV-1",
        "sourceFileType": "pdf",
        "parserName": parser_name,
        "parserVersion": "v1",
        "parserRuleVersion": f"{parser_name}-normalized-v1",
        "irVersion": "normalized-document-v1",
        "pages": [{"pageNo": 1, "width": 100, "height": 100, "unit": "pixel"}],
        "textBlocks": [
            {
                "textBlockId": "REV-1-block-1",
                "fileId": "FILE-1",
                "pageNo": 1,
                "textBlockType": "BODY",
                "rawText": "sample",
                "normalizedText": "sample",
                "parserName": parser_name,
                "parserVersion": "v1",
                "parserRuleVersion": f"{parser_name}-normalized-v1",
                "irVersion": "normalized-document-v1",
                "confidenceScore": 0.99,
                "confidenceStatus": "READABLE",
                "confidencePolicyVersion": "confidence-thresholds-v1",
                "coordinate": {
                    "sourceWidth": 100,
                    "sourceHeight": 100,
                    "sourceUnit": "pixel",
                    "x": 0,
                    "y": 0,
                    "width": 50,
                    "height": 20,
                    "normalizedX": 0,
                    "normalizedY": 0,
                    "normalizedWidth": 0.5,
                    "normalizedHeight": 0.2,
                    "coordinateConfidence": 0.99,
                },
            }
        ],
        "layoutBlocks": [],
        "tables": [],
        "warnings": [],
        "confidence": {
            "score": 0.99,
            "status": "READABLE",
            "policyVersion": "confidence-thresholds-v1",
        },
        "rawArtifactRef": "parser-service-v1",
        "createdAt": datetime.now(UTC).isoformat(),
    }


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body


def test_adapter_posts_document_and_validates_engine_owned_ir() -> None:
    adapter = ParserServiceAdapter("opendataloader-pdf", "http://engine:8091", timeout_seconds=1)
    with patch(
        "nh_ad_worker.parser_services.urlopen",
        return_value=nullcontext(_Response(json.dumps(_normalized(adapter.name)).encode())),
    ) as send:
        parsed = adapter.parse(_document())

    assert parsed.parser_name == "opendataloader-pdf"
    request = send.call_args.args[0]
    assert request.full_url == "http://engine:8091/v1/parse"
    assert json.loads(request.data or b"{}") == {
        "sourceFileId": "FILE-1",
        "reviewId": "REV-1",
        "fileName": "sample.pdf",
        "mimeType": "application/pdf",
        "contentBase64": "JVBERi1zYW1wbGU=",
    }


def test_adapter_rejects_cross_engine_identity() -> None:
    adapter = ParserServiceAdapter("rhwp", "http://engine:8093", timeout_seconds=1)
    with patch(
        "nh_ad_worker.parser_services.urlopen",
        return_value=nullcontext(_Response(json.dumps(_normalized("paddleocr")).encode())),
    ):
        with pytest.raises(ParserServiceError, match="RHWP_SERVICE_IDENTITY_MISMATCH"):
            adapter.parse(_document())
