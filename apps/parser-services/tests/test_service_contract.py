from __future__ import annotations

from pathlib import Path

from service import ParseRequest, normalized_document, page, text_block


def test_service_builds_parser_owned_normalized_document() -> None:
    request = ParseRequest(
        sourceFileId="FILE-1",
        reviewId="REV-1",
        fileName="ad.png",
        mimeType="image/png",
        contentBase64="aW1hZ2U=",
    )
    block = text_block(
        request,
        engine="paddleocr",
        index=1,
        page_no=1,
        text="광고 문구",
        source_width=100,
        source_height=50,
        x=10,
        y=5,
        width=30,
        height=10,
        confidence=0.9,
    )
    value = normalized_document(
        request,
        engine="paddleocr",
        version="v1",
        pages=[page(1, 100, 50)],
        blocks=[block],
    )

    assert value["parserName"] == "paddleocr"
    assert value["sourceFileId"] == "FILE-1"
    assert value["textBlocks"] == [block]
    assert block["coordinate"]["normalizedWidth"] == 0.3


def test_service_preserves_text_ir_offsets_when_an_engine_provides_them() -> None:
    request = ParseRequest(
        sourceFileId="FILE-1",
        reviewId="REV-1",
        fileName="ad.hwp",
        mimeType="application/x-hwp",
        contentBase64="aHdw",
    )
    block = text_block(
        request,
        engine="rhwp",
        index=1,
        page_no=1,
        text="광고 문구",
        source_width=100,
        source_height=50,
        x=0,
        y=0,
        width=100,
        height=50,
        confidence=0.95,
        text_path="pages/1",
        raw_start_offset=0,
        raw_end_offset=5,
    )

    assert block["textPath"] == "pages/1"
    assert block["rawStartOffset"] == 0
    assert block["normalizedEndOffset"] == 5


def test_hwpx_preview_keeps_document_text_and_removes_active_svg_nodes() -> None:
    from io import BytesIO
    from zipfile import ZipFile

    from rhwp_app import _hwpx_text_pages, _sanitize_svg

    source = BytesIO()
    with ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", "<root><t>광고 문구</t><t>유의사항</t></root>")
    assert _hwpx_text_pages(source.getvalue()) == [["광고 문구", "유의사항"]]
    safe = _sanitize_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" onclick="bad()"><script>alert(1)</script><text onclick="bad()">안전</text></svg>'.encode()
    )
    assert b"script" not in safe
    assert b"onclick" not in safe
    assert b"\xec\x95\x88\xec\xa0\x84" in safe


def test_rhwp_uses_text_export_for_hwp_review_input(monkeypatch, tmp_path) -> None:
    from rhwp_app import RhwpEngine

    def fake_run(command, **_kwargs):
        output = command[command.index("-o") + 1]
        Path(output).mkdir(parents=True)
        Path(output, "page-1.txt").write_text("대출 대상\n공무원", encoding="utf-8")

    monkeypatch.setattr("rhwp_app.subprocess.run", fake_run)
    monkeypatch.setattr(
        "rhwp_app.tempfile.TemporaryDirectory", lambda: _TemporaryDirectory(tmp_path)
    )

    assert RhwpEngine()._hwp_text_values("advertisement.hwp", b"hwp") == {
        1: [("대출 대상\n공무원", 0.0, 1.0)]
    }


class _TemporaryDirectory:
    def __init__(self, path) -> None:
        self.path = path

    def __enter__(self):
        return self.path

    def __exit__(self, *_args) -> None:
        return None
