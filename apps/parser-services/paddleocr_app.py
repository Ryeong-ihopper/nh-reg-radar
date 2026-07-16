"""PaddleOCR private service for image and scanned-PDF advertisements."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

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
            page_rows = [self._ocr.ocr(str(image), cls=True)[0] or [] for image in sources]
        if not any(page_rows):
            raise ValueError("no readable text")
        blocks: list[dict[str, object]] = []
        pages: list[dict[str, object]] = []
        index = 0
        for page_no, rows in enumerate(page_rows, start=1):
            if not rows:
                continue
            maximum_x = max(float(point[0]) for row in rows for point in row[0])
            maximum_y = max(float(point[1]) for row in rows for point in row[0])
            width, height = max(maximum_x, 1.0), max(maximum_y, 1.0)
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


app = app_for(PaddleOcrEngine())
