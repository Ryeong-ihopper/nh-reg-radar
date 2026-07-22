from __future__ import annotations

import json
from email.message import Message

from nh_ad_backend.pdf_preview import PaddlePdfPreviewAdapter


class _Response:
    def __init__(
        self, body: bytes, content_type: str = "application/json", total_pages: int = 0
    ) -> None:
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if total_pages:
            self.headers["X-Preview-Total-Pages"] = str(total_pages)

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_pdf_preview_metadata_and_page_are_cached_server_side(monkeypatch) -> None:
    requests: list[str] = []

    def fake_urlopen(request, **_kwargs):
        requests.append(request.full_url)
        if request.full_url.endswith("/metadata"):
            return _Response(json.dumps({"totalPages": 2}).encode())
        return _Response(b"\x89PNG\r\n\x1a\npage", "image/png", total_pages=2)

    monkeypatch.setattr("nh_ad_backend.pdf_preview.urlopen", fake_urlopen)
    adapter = PaddlePdfPreviewAdapter(
        "http://paddleocr:8092", timeout_seconds=1, cache_ttl_seconds=300, cache_max_bytes=1024
    )
    args = {
        "file_id": "FILE-1",
        "file_name": "ad.pdf",
        "mime_type": "application/pdf",
        "body": b"pdf",
    }

    assert adapter.describe(**args).total_pages == 2
    assert adapter.describe(**args).total_pages == 2
    assert adapter.render(**args, page_no=1).body.endswith(b"page")
    assert adapter.render(**args, page_no=1).body.endswith(b"page")

    assert requests == [
        "http://paddleocr:8092/v1/preview/metadata",
        "http://paddleocr:8092/v1/preview?pageNo=1",
    ]
