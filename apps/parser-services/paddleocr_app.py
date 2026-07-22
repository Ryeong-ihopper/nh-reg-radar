"""PaddleOCR private service for image and scanned-PDF advertisements."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from struct import unpack

from fastapi import HTTPException, Query, Response
from paddleocr import PaddleOCR

from service import ParseRequest, app_for, normalized_document, page, text_block


class PaddleOcrEngine:
    name = "paddleocr"

    def __init__(self) -> None:
        self._ocr = PaddleOCR(use_angle_cls=True, lang="korean", use_gpu=False, show_log=False)

    def parse(self, request: ParseRequest, body: bytes) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / request.file_name
            source.write_bytes(body)
            sources = (
                _render_pdf(source, root) if request.mime_type == "application/pdf" else [source]
            )
            page_dimensions = [_image_dimensions(image) for image in sources]
            page_rows = [self._ocr.ocr(str(image), cls=True)[0] or [] for image in sources]
        if not any(page_rows):
            raise ValueError("no readable text")
        blocks: list[dict[str, object]] = []
        pages: list[dict[str, object]] = []
        index = 0
        for page_no, (dimensions, rows) in enumerate(
            zip(page_dimensions, page_rows, strict=True), start=1
        ):
            if not rows:
                continue
            # OCR detections rarely reach the right/bottom page edge.  Those
            # maxima are not the source canvas and made every normalized box
            # drift when the preview retained the original full page.
            width, height = dimensions
            pages.append(page(page_no, width, height))
            for row in rows:
                index += 1
                points, recognition = row
                coordinates = [(float(point[0]), float(point[1])) for point in points]
                left, right = (
                    min(point[0] for point in coordinates),
                    max(point[0] for point in coordinates),
                )
                top, bottom = (
                    min(point[1] for point in coordinates),
                    max(point[1] for point in coordinates),
                )
                text, confidence = str(recognition[0]).strip(), float(recognition[1])
                if text:
                    blocks.append(
                        text_block(
                            request,
                            engine=self.name,
                            index=index,
                            page_no=page_no,
                            text=text,
                            source_width=width,
                            source_height=height,
                            x=left,
                            y=top,
                            width=max(right - left, 1.0),
                            height=max(bottom - top, 1.0),
                            confidence=confidence,
                        )
                    )
        if not blocks:
            raise ValueError("no readable text")
        return normalized_document(
            request, engine=self.name, version="v1", pages=pages, blocks=blocks
        )

    def preview(self, request: ParseRequest, body: bytes, page_no: int) -> tuple[bytes, int]:
        """Render a PDF page with the exact raster basis used for OCR boxes."""

        if request.mime_type != "application/pdf":
            raise ValueError("paddleocr preview accepts only PDF")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / request.file_name
            source.write_bytes(body)
            total_pages = _pdf_page_count(source)
            if page_no > total_pages:
                raise ValueError("preview page is out of range")
            return _render_pdf_page(source, root, page_no).read_bytes(), total_pages

    def preview_metadata(self, request: ParseRequest, body: bytes) -> int:
        if request.mime_type != "application/pdf":
            raise ValueError("paddleocr preview accepts only PDF")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / request.file_name
            source.write_bytes(body)
            return _pdf_page_count(source)


def _render_pdf(source: Path, root: Path) -> list[Path]:
    prefix = root / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "200", str(source), str(prefix)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    rendered = sorted(root.glob("page-*.png"))
    if not rendered:
        raise ValueError("PDF rendering produced no pages")
    return rendered


def _pdf_page_count(source: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(source)], check=True, capture_output=True, text=True, timeout=30
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.removeprefix("Pages:").strip())
    raise ValueError("pdfinfo did not report page count")


def _render_pdf_page(source: Path, root: Path, page_no: int) -> Path:
    """Render exactly one page at the OCR raster DPI for preview latency."""

    target = root / "preview"
    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-r",
            "200",
            "-f",
            str(page_no),
            "-l",
            str(page_no),
            "-singlefile",
            str(source),
            str(target),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    rendered = target.with_suffix(".png")
    if not rendered.is_file():
        raise ValueError("PDF preview rendering produced no page")
    return rendered


def _image_dimensions(source: Path) -> tuple[float, float]:
    """Read supported raster dimensions without a new image-library dependency."""

    data = source.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = unpack(">II", data[16:24])
        if width and height:
            return float(width), float(height)
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 <= len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            while marker == 0xFF and index < len(data):
                marker, index = data[index], index + 1
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(data):
                break
            size = unpack(">H", data[index : index + 2])[0]
            if size < 2 or index + size > len(data):
                break
            if (
                marker
                in {
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                }
                and size >= 7
            ):
                height, width = unpack(">HH", data[index + 3 : index + 7])
                if width and height:
                    return float(width), float(height)
            index += size
    raise ValueError("unsupported raster dimensions")


engine = PaddleOcrEngine()
app = app_for(engine)


@app.post("/v1/preview/metadata")
def preview_metadata(request: ParseRequest) -> dict[str, int]:
    try:
        return {"totalPages": engine.preview_metadata(request, request.body())}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="PADDLEOCR_PREVIEW_FAILED") from exc


@app.post("/v1/preview", response_class=Response)
def preview(
    request: ParseRequest, page_no: int = Query(alias="pageNo", ge=1, default=1)
) -> Response:
    try:
        body, total_pages = engine.preview(request, request.body(), page_no)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="PADDLEOCR_PREVIEW_FAILED") from exc
    return Response(
        content=body,
        media_type="image/png",
        headers={"X-Preview-Total-Pages": str(total_pages), "Cache-Control": "no-store"},
    )
