"""Read actual rendered-PDF text geometry, without OCR or inferred positions."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pypdfium2 as pdfium


def pdf_text_layout(pdf: bytes) -> dict:
    pages = []
    scale = 200 / 72
    with pdfium.PdfDocument(pdf) as document:
        for index in range(len(document)):
            page = document[index]
            width, height = page.get_size()
            textpage = page.get_textpage()
            lines, chars, boxes = [], [], []

            def flush():
                text = "".join(chars).strip()
                if text and boxes:
                    lines.append({"line_ref": f"render-p{index + 1}/L{len(lines) + 1}", "text": text,
                                  "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                           max(b[2] for b in boxes), max(b[3] for b in boxes)]})
                chars.clear()
                boxes.clear()

            for char_index in range(textpage.count_chars()):
                char = textpage.get_text_range(char_index, 1)
                if char in {"\r", "\n"}:
                    flush()
                    continue
                chars.append(char)
                if not char.strip():
                    continue
                left, bottom, right, top = textpage.get_charbox(char_index)
                box = [left * scale, (height - top) * scale, right * scale, (height - bottom) * scale]
                if all(math.isfinite(x) for x in box) and box[2] > box[0] and box[3] > box[1]:
                    boxes.append(box)
            flush()
            textpage.close()
            page.close()
            pages.append({"page_no": index + 1, "source_page_no": index + 1,
                          "canvas_w": math.ceil(width * scale), "canvas_h": math.ceil(height * scale),
                          "regions": [{"region_id": f"render-p{index + 1}", "lines": lines}]})
    return {"source": "HWP 200-DPI render + parser visual projection", "pages": pages,
            "coordinate_source": "CONVERTED_PDF_TEXT", "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "counts": {"pages": len(pages), "regions": len(pages),
                       "lines": sum(len(p["regions"][0]["lines"]) for p in pages)}}


def load_or_render(source: Path, directory: Path, renderer) -> dict:
    body = source.read_bytes()
    pdf_path = directory / "rendered-original.pdf"
    if pdf_path.is_file():
        pdf = pdf_path.read_bytes()
    else:
        pdf = renderer.pdf_bytes(body, source.name)
        pdf_path.write_bytes(pdf)
    return pdf_text_layout(pdf)
