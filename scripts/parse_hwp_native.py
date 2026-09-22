"""Connect the installed HWP text extractor to the existing P1/P3 boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def build_pair(source: Path, native: dict, template_id: str) -> tuple[dict, dict]:
    """Keep declared text/style; a logical HWP page never claims physical bbox."""
    regions, projections = [], []
    for page in native.get("pages") or []:
        for region in page.get("regions") or []:
            for line in region.get("lines") or []:
                text = str(line.get("text") or "")
                if not text.strip():
                    continue
                rid = f"native-r{len(regions) + 1:04d}"
                ref = f"p1/{rid}/L1"
                regions.append({"region_id": rid, "bbox": None, "layout": None,
                    "lines": [{"line_ref": ref, "parser_text": text, "text_source": "digital",
                               "bbox": None, "style": line.get("style")}],
                })
                projections.append({"region_id": rid, "review_text": text, "text_source": "digital",
                    "line_refs": [ref], "labels": [],
                    "text_selection": {"needs_review": False, "selection_status": "native_digital",
                                       "reason": "document-processor native text; no VLM rewriting"}})
    if not regions:
        raise ValueError("HWP_NATIVE_EMPTY: no readable native text")
    identity = {"doc_id": source.stem, "source_file": source.name,
                "file_type": source.suffix.lstrip(".").lower()}
    template = {"template_id": template_id, "source": "user_provided"}
    p1 = {**identity, "reading_evidence_contract": {"version": "nh-ad-review-evidence-v6"},
          "template": template, "classification": {},
          "pages": [{"page_no": 1, "canvas_w": None, "canvas_h": None,
                     "parse_route": "native_hwp", "parse_status": "ok", "regions": regions}],
          "coverage": {"complete_document_read": True},
          "notes": ["Logical native text page; physical display positions require verified PDF alignment."]}
    p3 = {"contract": {"version": "nh-ad-review-region-input-v1"},
          "document": {**identity, "template": template},
          "pages": [{"page_no": 1, "regions": projections}],
          "diagnostics": {"native_hwp": {"extractor": "nh_parser_fin.ingest.hwp.ingest_hwp",
                          "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                          "physical_page_assignment": "UNAVAILABLE", "native_line_count": len(regions)}}}
    return p1, p3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parser-root", type=Path, required=True)
    parser.add_argument("--template-id", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.parser_root))
    from document_processor import DocIR
    from nh_parser_fin.ingest.assets import decode_asset_image, is_decorative, iter_assets
    from nh_parser_fin.ingest.hwp import ingest_hwp

    docir = DocIR.from_file(str(args.source))
    # Existing image-bearing HWP remains on its OCR/VLM route. Do not silently
    # call a native-only parse complete when an embedded advertisement is unread.
    for _, asset in iter_assets(docir):
        image = decode_asset_image(asset)
        if image is None or not is_decorative(*image.size):
            return 3
    native = ingest_hwp(args.source).model_dump(mode="json")
    p1, p3 = build_pair(args.source, native, args.template_id)
    directory = args.output / "final"
    directory.mkdir(parents=True, exist_ok=True)
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in args.source.name)
    for suffix, data in (("p1", p1), ("p3", p3), ("native", native)):
        (directory / f"{stem}.{suffix}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"route": "native_hwp", "lines": len(p1["pages"][0]["regions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
