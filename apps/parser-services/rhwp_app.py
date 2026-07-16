"""rhwp CLI private service for HWP/HWPX advertisements."""

from __future__ import annotations

import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from service import ParseRequest, app_for, normalized_document, page, text_block


class RhwpEngine:
    name = "rhwp"

    def parse(self, request: ParseRequest, body: bytes) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / request.file_name
            output = root / "output"
            source.write_bytes(body)
            subprocess.run(
                ["rhwp", "export-svg", str(source), "-o", str(output)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            svg_pages = sorted(output.rglob("*.svg"))
            page_values = {
                page_no: _svg_text(svg) for page_no, svg in enumerate(svg_pages, start=1)
            }
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


def _svg_text(path: Path) -> list[tuple[str, float, float]]:
    root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
    values: list[tuple[str, float, float]] = []
    for element in root.iter():
        if not element.tag.endswith("text"):
            continue
        text = "".join(element.itertext()).strip()
        if not text:
            continue
        values.append((text, float(element.attrib.get("x", 0)), float(element.attrib.get("y", 0))))
    return values


app = app_for(RhwpEngine())
