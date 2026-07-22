"""Private PDF preview adapter aligned with the PaddleOCR raster coordinate basis."""

from __future__ import annotations

import base64
import json
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from time import monotonic
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PdfPreviewError(RuntimeError):
    """The private PDF renderer could not produce a safe preview."""


@dataclass(frozen=True)
class PdfPreview:
    body: bytes
    total_pages: int


@dataclass(frozen=True)
class PdfPreviewMetadata:
    total_pages: int


class PdfPreviewRenderer(Protocol):
    def describe(
        self, *, file_id: str, file_name: str, mime_type: str, body: bytes
    ) -> PdfPreviewMetadata: ...

    def render(
        self, *, file_id: str, file_name: str, mime_type: str, body: bytes, page_no: int
    ) -> PdfPreview: ...


class PaddlePdfPreviewAdapter:
    """Render the page using the same 200-DPI raster as PaddleOCR."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float,
        cache_ttl_seconds: float = 300,
        cache_max_bytes: int = 128 * 1024 * 1024,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_max_bytes = cache_max_bytes
        self._page_cache: OrderedDict[tuple[str, int], tuple[float, PdfPreview]] = OrderedDict()
        self._metadata_cache: OrderedDict[str, tuple[float, PdfPreviewMetadata]] = OrderedDict()
        self._cache_bytes = 0
        self._lock = RLock()

    @staticmethod
    def _payload(file_id: str, file_name: str, mime_type: str, body: bytes) -> bytes:
        return json.dumps(
            {
                "sourceFileId": file_id,
                "reviewId": f"preview-{file_id}",
                "fileName": file_name,
                "mimeType": mime_type,
                "contentBase64": base64.b64encode(body).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")

    def describe(
        self, *, file_id: str, file_name: str, mime_type: str, body: bytes
    ) -> PdfPreviewMetadata:
        key = sha256(body).hexdigest()
        now = monotonic()
        with self._lock:
            cached = self._metadata_cache.get(key)
            if cached is not None and cached[0] > now:
                self._metadata_cache.move_to_end(key)
                return cached[1]
            self._metadata_cache.pop(key, None)
        request = Request(
            f"{self._endpoint}/v1/preview/metadata",
            data=self._payload(file_id, file_name, mime_type, body),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                value = json.loads(bytes(response.read()))
        except HTTPError as exc:
            if exc.code in {400, 404, 422}:
                raise PdfPreviewError("PDF_PREVIEW_FAILED") from exc
            raise PdfPreviewError("PDF_PREVIEW_UNAVAILABLE") from exc
        except (URLError, TimeoutError, ValueError, TypeError) as exc:
            raise PdfPreviewError("PDF_PREVIEW_UNAVAILABLE") from exc
        try:
            metadata = PdfPreviewMetadata(total_pages=int(value["totalPages"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PdfPreviewError("PDF_PREVIEW_FAILED") from exc
        if metadata.total_pages < 1:
            raise PdfPreviewError("PDF_PREVIEW_FAILED")
        with self._lock:
            self._metadata_cache[key] = (now + self._cache_ttl_seconds, metadata)
            self._metadata_cache.move_to_end(key)
            while len(self._metadata_cache) > 256:
                self._metadata_cache.popitem(last=False)
        return metadata

    def render(
        self, *, file_id: str, file_name: str, mime_type: str, body: bytes, page_no: int
    ) -> PdfPreview:
        key = (sha256(body).hexdigest(), page_no)
        now = monotonic()
        with self._lock:
            cached = self._page_cache.get(key)
            if cached is not None and cached[0] > now:
                self._page_cache.move_to_end(key)
                return cached[1]
            if cached is not None:
                self._cache_bytes -= len(cached[1].body)
                del self._page_cache[key]
        request = Request(
            f"{self._endpoint}/v1/preview?{urlencode({'pageNo': page_no})}",
            data=self._payload(file_id, file_name, mime_type, body),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "image/png"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                rendered = bytes(response.read())
                total_pages = int(response.headers.get("X-Preview-Total-Pages", "0"))
                content_type = response.headers.get_content_type()
        except HTTPError as exc:
            if exc.code in {400, 404, 422}:
                raise PdfPreviewError("PDF_PREVIEW_FAILED") from exc
            raise PdfPreviewError("PDF_PREVIEW_UNAVAILABLE") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise PdfPreviewError("PDF_PREVIEW_UNAVAILABLE") from exc
        if (
            content_type != "image/png"
            or total_pages < 1
            or not rendered.startswith(b"\x89PNG\r\n\x1a\n")
            or len(rendered) > 25 * 1024 * 1024
        ):
            raise PdfPreviewError("PDF_PREVIEW_FAILED")
        preview = PdfPreview(body=rendered, total_pages=total_pages)
        with self._lock:
            self._metadata_cache[key[0]] = (
                now + self._cache_ttl_seconds,
                PdfPreviewMetadata(total_pages=total_pages),
            )
            self._metadata_cache.move_to_end(key[0])
            self._page_cache[key] = (now + self._cache_ttl_seconds, preview)
            self._page_cache.move_to_end(key)
            self._cache_bytes += len(preview.body)
            while len(self._metadata_cache) > 256:
                self._metadata_cache.popitem(last=False)
            while self._page_cache and self._cache_bytes > self._cache_max_bytes:
                _expired_key, (_expires_at, expired) = self._page_cache.popitem(last=False)
                self._cache_bytes -= len(expired.body)
        return preview
