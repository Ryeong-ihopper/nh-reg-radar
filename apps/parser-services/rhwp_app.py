"""rhwp CLI private service for HWP/HWPX advertisements."""

from __future__ import annotations

import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

from fastapi import HTTPException, Query, Response

from service import ParseRequest, app_for, normalized_document, page, text_block


class RhwpEngine:
    name = "rhwp"

    def parse(self, request: ParseRequest, body: bytes) -> dict[str, object]:
        page_values = self._page_values(request.file_name, body)
        if not any(page_values.values()):
            raise ValueError("rhwp emitted no text")
        # rhwp emits SVG glyph-level text nodes for some HWP documents.  Keep one
        # source-addressable block per page instead of turning a single ad into
        # thousands of LLM review inputs.
        blocks: list[dict[str, object]] = []
        pages: list[dict[str, object]] = []
        for page_no, values in page_values.items():
            if not values:
                continue
            width = max(x for _, x, _ in values) + 1.0
            height = max(y for _, _, y in values) + 1.0
            pages.append(page(page_no, width, height))
            content = "\n".join(text for text, _, _ in values)
            blocks.append(
                text_block(
                    request,
                    engine=self.name,
                    index=len(blocks) + 1,
                    page_no=page_no,
                    text=content,
                    source_width=width,
                    source_height=height,
                    x=0.0,
                    y=0.0,
                    width=width,
                    height=height,
                    confidence=0.95,
                    text_path=f"pages/{page_no}",
                    raw_start_offset=0,
                    raw_end_offset=len(content),
                )
            )
        return normalized_document(
            request, engine=self.name, version="v1", pages=pages, blocks=blocks
        )

    def preview(self, request: ParseRequest, body: bytes, page_no: int) -> tuple[bytes, int]:
        """Return a sanitized, single-page SVG without exposing the source document."""
        if Path(request.file_name).suffix.casefold() == ".hwpx":
            pages = self._hwpx_svg_pages(body)
        else:
            pages = self._hwp_svg_pages(request.file_name, body)
        if page_no > len(pages):
            raise ValueError("preview page is out of range")
        return _sanitize_svg(pages[page_no - 1]), len(pages)

    def _page_values(
        self, file_name: str, body: bytes
    ) -> dict[int, list[tuple[str, float, float]]]:
        if Path(file_name).suffix.casefold() == ".hwpx":
            return {
                index: [(text, 0.0, float(line)) for line, text in enumerate(values, start=1)]
                for index, values in enumerate(_hwpx_text_pages(body), start=1)
            }
        return self._hwp_text_values(file_name, body)

    def _hwp_text_values(
        self, file_name: str, body: bytes
    ) -> dict[int, list[tuple[str, float, float]]]:
        """Use rhwp's semantic text export, not its glyph-level SVG, for review input."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / file_name
            output = root / "text"
            source.write_bytes(body)
            subprocess.run(
                ["rhwp", "export-text", str(source), "-o", str(output)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            pages = [
                page_text.read_text(encoding="utf-8").strip()
                for page_text in sorted(output.rglob("*.txt"))
            ]
        if not any(pages):
            raise ValueError("rhwp emitted no text")
        return {
            page_no: [(text, 0.0, float(page_no))]
            for page_no, text in enumerate(pages, start=1)
            if text
        }

    def _hwp_svg_pages(self, file_name: str, body: bytes) -> list[bytes]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / file_name
            output = root / "output"
            source.write_bytes(body)
            subprocess.run(
                ["rhwp", "export-svg", str(source), "-o", str(output)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            pages = [svg.read_bytes() for svg in sorted(output.rglob("*.svg"))]
        if not pages:
            raise ValueError("rhwp emitted no pages")
        return pages

    def _hwpx_svg_pages(self, body: bytes) -> list[bytes]:
        text_pages = _hwpx_text_pages(body)
        if not text_pages:
            raise ValueError("hwpx emitted no text")
        return [_text_svg(lines) for lines in text_pages]


def _hwpx_text_pages(body: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(body)) as archive:
            names = sorted(
                name
                for name in archive.namelist()
                if name.casefold().startswith("contents/section")
                and name.casefold().endswith(".xml")
            )
            values = []
            for name in names:
                root = ElementTree.fromstring(archive.read(name))
                lines = [
                    "".join(element.itertext()).strip()
                    for element in root.iter()
                    if element.tag.rsplit("}", 1)[-1] == "t"
                ]
                values.append([line for line in lines if line])
    except (ElementTree.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError("hwpx content is invalid") from exc
    return [page for page in values if page]


def _text_svg(lines: list[str]) -> bytes:
    root = ElementTree.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": "0 0 1240 1754",
            "role": "img",
            "aria-label": "HWPX 문서 미리보기",
        },
    )
    ElementTree.SubElement(root, "rect", {"width": "1240", "height": "1754", "fill": "white"})
    text = ElementTree.SubElement(
        root,
        "text",
        {
            "x": "96",
            "y": "120",
            "fill": "#172019",
            "font-size": "28",
            "font-family": "Noto Sans KR, sans-serif",
        },
    )
    for index, line in enumerate(lines[:45]):
        node = ElementTree.SubElement(text, "tspan", {"x": "96", "dy": "34" if index else "0"})
        node.text = line
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _sanitize_svg(value: bytes) -> bytes:
    root = ElementTree.fromstring(value)
    forbidden = {
        "script",
        "foreignObject",
        "iframe",
        "object",
        "embed",
        "image",
        "use",
        "a",
        "animate",
        "set",
    }
    for node in root.iter():
        for name, attribute in list(node.attrib.items()):
            if (
                name.casefold().startswith("on")
                or "href" in name.casefold()
                or "url(" in attribute.casefold()
            ):
                del node.attrib[name]
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] in forbidden:
                parent.remove(child)
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


app = app_for(RhwpEngine())


@app.post("/v1/preview", response_class=Response)
def preview(
    request: ParseRequest, page_no: int = Query(alias="pageNo", ge=1, default=1)
) -> Response:
    try:
        body, total_pages = RhwpEngine().preview(request, request.body(), page_no)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="RHWP_PREVIEW_FAILED") from exc
    return Response(
        content=body,
        media_type="image/svg+xml",
        headers={"X-Preview-Total-Pages": str(total_pages), "Cache-Control": "no-store"},
    )
