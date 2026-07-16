"""OpenDataLoader PDF private service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import opendataloader_pdf

from service import ParseRequest, app_for, normalized_document, page, text_block


class OpenDataLoaderEngine:
    name = "opendataloader-pdf"

    def parse(self, request: ParseRequest, body: bytes) -> dict[str, object]:
        if request.mime_type != "application/pdf":
            raise ValueError("PDF only")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / request.file_name
            output = root / "output"
            source.write_bytes(body)
            opendataloader_pdf.convert(
                input_path=[str(source)], output_dir=str(output), format="json"
            )
            values = _load_elements(output)
        if not values:
            raise ValueError("no extractable PDF text")
        width = max(item[4] for item in values)
        height = max(item[5] for item in values)
        blocks = [
            text_block(
                request,
                engine=self.name,
                index=index,
                page_no=item[0],
                text=item[1],
                source_width=width,
                source_height=height,
                x=item[2],
                y=item[3],
                width=max(item[4] - item[2], 1.0),
                height=max(item[5] - item[3], 1.0),
                confidence=0.99,
            )
            for index, item in enumerate(values, start=1)
        ]
        pages = [page(number, width, height) for number in sorted({item[0] for item in values})]
        return normalized_document(
            request, engine=self.name, version="v1", pages=pages, blocks=blocks
        )


def _load_elements(output: Path) -> list[tuple[int, str, float, float, float, float]]:
    json_files = list(output.rglob("*.json"))
    if not json_files:
        raise ValueError("OpenDataLoader did not produce JSON")
    values: list[tuple[int, str, float, float, float, float]] = []
    for candidate in json_files:
        values.extend(_walk(json.loads(candidate.read_text(encoding="utf-8")), 1))
    return values


def _walk(value: object, page_no: int) -> list[tuple[int, str, float, float, float, float]]:
    if isinstance(value, list):
        return [item for child in value for item in _walk(child, page_no)]
    if not isinstance(value, dict):
        return []
    current_page = int(value.get("page number", value.get("pageNumber", page_no)) or page_no)
    text = value.get("content", value.get("text"))
    box = value.get("bounding box", value.get("boundingBox"))
    if isinstance(text, str) and text.strip() and isinstance(box, list) and len(box) == 4:
        try:
            left, bottom, right, top = (float(number) for number in box)
            return [(current_page, text.strip(), left, bottom, right, top)]
        except (TypeError, ValueError):
            pass
    return [item for child in value.values() for item in _walk(child, current_page)]


app = app_for(OpenDataLoaderEngine())
