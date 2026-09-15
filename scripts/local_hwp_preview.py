"""Local HWP preview support for the loopback operational demonstration."""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import pypdfium2 as pdfium

from nh_ad_backend.hwp_preview import HwpPreview, HwpPreviewError


def resolve_soffice() -> Path:
    configured = os.environ.get("NH_LOCAL_SOFFICE")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files\LibreOffice\program\soffice.com"),
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise HwpPreviewError("HWP_PREVIEW_UNAVAILABLE")


def convert_hwp_to_pdf(body: bytes, file_name: str) -> bytes:
    """Convert in a private temporary directory and return only PDF bytes."""
    suffix = Path(file_name).suffix.casefold()
    if suffix not in {".hwp", ".hwpx"}:
        raise HwpPreviewError("HWP_PREVIEW_FAILED")
    with tempfile.TemporaryDirectory(prefix="nh-hwp-preview-") as directory:
        root = Path(directory)
        source = root / f"input{suffix}"
        source.write_bytes(body)
        try:
            result = subprocess.run(
                [str(resolve_soffice()), "--headless", "--convert-to", "pdf",
                 "--outdir", str(root), str(source)],
                check=False,
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HwpPreviewError("HWP_PREVIEW_UNAVAILABLE") from exc
        output = root / "input.pdf"
        if result.returncode or not output.is_file():
            raise HwpPreviewError("HWP_PREVIEW_FAILED")
        value = output.read_bytes()
    if not value.startswith(b"%PDF-"):
        raise HwpPreviewError("HWP_PREVIEW_FAILED")
    return value


class LocalHwpPreview:
    """Render HWP/HWPX at the parser visual projection's 200-DPI basis."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pdf_cache: dict[str, bytes] = {}
        self._page_cache: dict[tuple[str, int], HwpPreview] = {}

    def pdf_bytes(self, body: bytes, file_name: str) -> bytes:
        key = hashlib.sha256(body).hexdigest()
        with self._lock:
            cached = self._pdf_cache.get(key)
        if cached is not None:
            return cached
        converted = convert_hwp_to_pdf(body, file_name)
        with self._lock:
            self._pdf_cache[key] = converted
        return converted

    def render(self, *, file_id: str, file_name: str, mime_type: str,
               body: bytes, page_no: int) -> HwpPreview:
        del file_id, mime_type
        digest = hashlib.sha256(body).hexdigest()
        cache_key = (digest, page_no)
        with self._lock:
            cached = self._page_cache.get(cache_key)
        if cached is not None:
            return cached
        pdf_body = self.pdf_bytes(body, file_name)
        try:
            with pdfium.PdfDocument(pdf_body) as document:
                if page_no < 1 or page_no > len(document):
                    raise HwpPreviewError("HWP_PREVIEW_FAILED")
                page = document[page_no - 1]
                bitmap = page.render(scale=200 / 72)
                output = io.BytesIO()
                bitmap.to_pil().save(output, format="PNG")
                preview = HwpPreview(output.getvalue(), len(document))
                bitmap.close()
                page.close()
        except HwpPreviewError:
            raise
        except Exception as exc:
            raise HwpPreviewError("HWP_PREVIEW_FAILED") from exc
        with self._lock:
            self._page_cache[cache_key] = preview
        return preview
