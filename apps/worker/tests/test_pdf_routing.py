from __future__ import annotations

from pathlib import Path

from nh_ad_worker.postgres import _is_scanned_pdf


def test_image_only_pdf_is_routed_to_paddleocr() -> None:
    assert _is_scanned_pdf(
        file_name="NH농협은행-2026_001-예금성.pdf",
        mime_type="application/pdf",
        body=Path("docs/광고예시/NH농협은행-2026_001-예금성.pdf").read_bytes(),
    )


def test_non_pdf_is_not_marked_as_scanned() -> None:
    assert (
        _is_scanned_pdf(file_name="advertisement.png", mime_type="image/png", body=b"image")
        is False
    )
