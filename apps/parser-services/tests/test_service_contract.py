from __future__ import annotations

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
