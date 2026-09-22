"""Synthetic native HWP contract and converted-PDF geometry regressions."""
import json
from unittest.mock import patch

import pytest

from parse_hwp_native import build_pair
from hwp_pdf_layout import pdf_text_layout
from local_hwp_preview import LocalHwpPreview
from rag.parsing.prepare_inputs import combine


def test_native_body_styles_and_refs_survive_contract(tmp_path):
    source = tmp_path / "not-a-product.hwp"
    source.write_bytes(b"synthetic")
    native = {"pages": [{"regions": [{"lines": [
        {"text": "Alpha condition", "style": {"bold": True}},
        {"text": "Table A | value 42"}, {"text": " "},
    ]}]}]}
    p1, p3 = build_pair(source, native, "selected-template")
    paths = [tmp_path / "p1.json", tmp_path / "p3.json"]
    for path, data in zip(paths, (p1, p3)):
        path.write_text(json.dumps(data), encoding="utf-8")
    combined = combine(*paths)
    regions = combined["pages"][0]["regions"]
    assert [r["final_text"] for r in regions] == ["Alpha condition", "Table A | value 42"]
    assert all(r["lines"][0]["bbox"] is None for r in regions)
    assert regions[0]["lines"][0]["style"] == {"bold": True}
    assert p1["classification"] == {}
    assert p3["document"]["template"]["template_id"] == "selected-template"
    assert combined["pages"][0]["parse_route"] == "native_hwp"
    with pytest.raises(ValueError, match="HWP_NATIVE_EMPTY"):
        build_pair(source, {"pages": []}, "selected-template")


def synthetic_pdf():
    stream = b"BT /F1 12 Tf 20 150 Td (Alpha condition) Tj 0 -20 Td (Table value) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    body, offsets = b"%PDF-1.4\n", [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{index} 0 obj\n".encode() + value + b"\nendobj\n"
    start = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return body + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()


def test_actual_pdf_character_coordinates_match_render_size():
    pdf = synthetic_pdf()
    layout = pdf_text_layout(pdf)
    page = layout["pages"][0]
    assert (page["canvas_w"], page["canvas_h"]) == (556, 556)
    lines = page["regions"][0]["lines"]
    assert [row["text"] for row in lines] == ["Alpha condition", "Table value"]
    assert all(0 <= row["bbox"][0] < row["bbox"][2] <= 556 for row in lines)
    assert lines[0]["bbox"][1] < lines[1]["bbox"][1]
    assert layout["coordinate_source"] == "CONVERTED_PDF_TEXT"


def test_pdf_preview_cache_survives_restart_and_is_source_specific(tmp_path):
    pdf = synthetic_pdf()
    with patch("local_hwp_preview.convert_hwp_to_pdf", return_value=pdf) as convert:
        assert LocalHwpPreview(tmp_path).pdf_bytes(b"source-one", "a.hwp") == pdf
        assert LocalHwpPreview(tmp_path).pdf_bytes(b"source-one", "renamed.hwp") == pdf
        assert convert.call_count == 1
        LocalHwpPreview(tmp_path).pdf_bytes(b"source-two", "a.hwp")
        assert convert.call_count == 2
