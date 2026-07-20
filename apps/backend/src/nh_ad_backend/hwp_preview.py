"""Private adapter for on-demand HWP/HWPX preview rendering."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HwpPreviewError(RuntimeError):
    """The private renderer could not produce a safe preview."""


@dataclass(frozen=True)
class HwpPreview:
    body: bytes
    total_pages: int


class HwpPreviewRenderer(Protocol):
    def render(
        self, *, file_id: str, file_name: str, mime_type: str, body: bytes, page_no: int
    ) -> HwpPreview: ...


class RhwpPreviewAdapter:
    """Keep raw document conversion behind the private rhwp service boundary."""

    def __init__(self, endpoint: str, *, timeout_seconds: float) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def render(
        self, *, file_id: str, file_name: str, mime_type: str, body: bytes, page_no: int
    ) -> HwpPreview:
        payload = {
            "sourceFileId": file_id,
            "reviewId": f"preview-{file_id}",
            "fileName": file_name,
            "mimeType": mime_type,
            "contentBase64": base64.b64encode(body).decode("ascii"),
        }
        request = Request(
            f"{self._endpoint}/v1/preview?{urlencode({'pageNo': page_no})}",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "image/svg+xml"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                rendered = bytes(response.read())
                total_pages = int(response.headers.get("X-Preview-Total-Pages", "0"))
                content_type = response.headers.get_content_type()
        except HTTPError as exc:
            if exc.code in {400, 404, 422}:
                raise HwpPreviewError("HWP_PREVIEW_FAILED") from exc
            raise HwpPreviewError("HWP_PREVIEW_UNAVAILABLE") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise HwpPreviewError("HWP_PREVIEW_UNAVAILABLE") from exc
        if (
            content_type != "image/svg+xml"
            or total_pages < 1
            or len(rendered) > 10 * 1024 * 1024
            # ElementTree may serialise a namespace-qualified root as ``<ns0:svg``.
            # The private renderer has already sanitized the document; accept either
            # spelling while still rejecting non-SVG response bodies.
            or b"svg" not in rendered[:1024].lower()
        ):
            raise HwpPreviewError("HWP_PREVIEW_FAILED")
        return HwpPreview(body=rendered, total_pages=total_pages)
