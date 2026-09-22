"""Audit saved viewer citations against exact parser lines and bounding boxes."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    exported, layout = read(args.export), read(args.layout)
    lines: dict[str, dict] = {}
    for page in layout.get("pages") or []:
        for region in page.get("regions") or []:
            for line in region.get("lines") or []:
                ref = str(line.get("line_ref") or "")
                if not ref or ref in lines:
                    raise ValueError(f"missing or duplicate parser line_ref: {ref!r}")
                lines[ref] = {
                    "text": str(line.get("text") or ""),
                    "pageNo": page["page_no"],
                    "bbox": line["bbox"],
                    "width": page["canvas_w"],
                    "height": page["canvas_h"],
                    "asset_id": page.get("asset_id"),
                    "source_page_no": page.get("source_page_no"),
                }

    errors, row_reports = [], []
    rows = [*(exported.get("results") or []), *(exported.get("review_candidates") or [])]
    for row in rows:
        row_id = str(row.get("row_id") or row.get("item_id") or "")
        refs = [str(value) for value in row.get("evidence_line_refs") or []]
        missing = [ref for ref in refs if ref not in lines]
        if missing:
            errors.append({"row": row_id, "code": "UNKNOWN_LINE_REF", "values": missing})
        exact = [lines[ref] for ref in refs if ref in lines]
        expected_text = "\n".join(value["text"] for value in exact)
        if refs and normalized(row.get("evidence")) != normalized(expected_text):
            errors.append({"row": row_id, "code": "EVIDENCE_TEXT_DIFFERS_FROM_LINES"})

        authoritative_locations = row.get("evidence_locations") or (
            row.get("review_locations") or []
            if row.get("verdict") == "판단불가" else []
        )
        line_locations = {
            str(location.get("key")): location
            for location in authoritative_locations
            if location.get("precision") == "LINE"
        }
        for ref in refs:
            if ref not in lines:
                continue
            location = line_locations.get(ref)
            if location is None:
                errors.append({"row": row_id, "code": "CITED_LINE_HAS_NO_EXACT_BOX", "value": ref})
                continue
            expected = lines[ref]
            for field in ("pageNo", "bbox", "width", "height", "asset_id", "source_page_no"):
                if location.get(field) != expected[field]:
                    errors.append({"row": row_id, "code": "LINE_BOX_FIELD_MISMATCH",
                                   "value": ref, "field": field})
        for ref in line_locations:
            if ref not in refs:
                errors.append({"row": row_id, "code": "UNCITED_LINE_BOX", "value": ref})

        locations = authoritative_locations
        expected_status = "MAPPED" if locations else None
        if expected_status and row.get("evidence_location_status") != expected_status:
            errors.append({"row": row_id, "code": "LOCATION_STATUS_MISMATCH"})
        row_reports.append({
            "row_id": row_id,
            "item_id": row.get("item_id"),
            "verdict": row.get("verdict"),
            "cited_lines": len(refs),
            "exact_line_boxes": len(line_locations),
            "approximate_region_boxes": sum(
                location.get("precision") == "REGION" for location in locations
            ),
            "grounding_guard_status": (row.get("model_assessment") or {}).get("status"),
        })

    report = {
        "schema_version": "operational-evidence-geometry-audit-v1",
        "status": "PASS" if not errors else "FAIL",
        "scope": "citation_text_line_ref_and_bbox_identity",
        "semantic_accuracy_scored": False,
        "counts": {
            "rows": len(rows),
            "parser_lines": len(lines),
            "rows_with_citations": sum(bool(row.get("evidence_line_refs")) for row in rows),
            "rows_with_exact_line_boxes": sum(bool(
                row.get("evidence_locations") or row.get("review_locations")
            ) for row in rows),
            "errors": len(errors),
        },
        "errors": errors,
        "rows": row_reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["counts"]}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
