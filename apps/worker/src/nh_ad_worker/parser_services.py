"""Private HTTP adapters for ADR-0072 parser/OCR engine services."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nh_ad_parser_contracts import DocumentInput, NormalizedDocument, ParserAdapter


class ParserServiceError(RuntimeError):
    """An engine service did not return a usable normalized document."""


class ParserServiceAdapter:
    """Keep engine transport outside the review pipeline and validate its IR."""

    def __init__(self, name: str, endpoint: str, *, timeout_seconds: float) -> None:
        self.name = name
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        payload = {
            "sourceFileId": document.source_file_id,
            "reviewId": document.review_id,
            "fileName": document.file_name,
            "mimeType": document.mime_type,
            "contentBase64": base64.b64encode(document.body).decode("ascii"),
        }
        request = Request(
            f"{self._endpoint}/v1/parse",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                body = bytes(response.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ParserServiceError(f"{self.name.upper()}_SERVICE_UNAVAILABLE") from exc
        try:
            value = json.loads(body)
            normalized = NormalizedDocument.model_validate(value)
        except (TypeError, ValueError) as exc:
            raise ParserServiceError(f"{self.name.upper()}_SERVICE_INVALID_RESPONSE") from exc
        if (
            normalized.review_id != document.review_id
            or normalized.source_file_id != document.source_file_id
            or normalized.parser_name != self.name
        ):
            raise ParserServiceError(f"{self.name.upper()}_SERVICE_IDENTITY_MISMATCH")
        return normalized


def parser_service_adapters(
    *,
    opendataloader_endpoint: str,
    paddleocr_endpoint: str,
    rhwp_endpoint: str,
    timeout_seconds: float,
) -> dict[str, ParserAdapter]:
    """Build the only ADR-0072 engine adapters exposed to the router."""

    return {
        "opendataloader-pdf": ParserServiceAdapter(
            "opendataloader-pdf", opendataloader_endpoint, timeout_seconds=timeout_seconds
        ),
        "paddleocr": ParserServiceAdapter(
            "paddleocr", paddleocr_endpoint, timeout_seconds=timeout_seconds
        ),
        "rhwp": ParserServiceAdapter("rhwp", rhwp_endpoint, timeout_seconds=timeout_seconds),
    }
