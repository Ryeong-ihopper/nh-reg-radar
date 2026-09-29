"""Adapt supported parser P1/P3 revisions to the canonical RAG boundary.

The adapter is deliberately a structural translation only.  It does not infer
product routing, create visibility measurements, change parser text, or merge
regions.  The original parser JSON remains the on-disk audit source; callers
record its hashes before this in-memory projection is consumed.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any


CANONICAL_P1 = "nh-ad-review-evidence-v6"
CANONICAL_P3 = "nh-ad-review-region-input-v1"
EXTERNAL_P1 = "nh-ad-parse-evidence-v1"
EXTERNAL_P3 = "nh-ad-region-review-input-v1"
PARSER_FIN_P1 = "nh-ad-parse-evidence-v3"
PARSER_FIN_P3 = "nh-ad-region-review-input-v6"
PARSER_FIN_CURRENT_P1 = "nh-ad-parse-evidence-v4"
PARSER_FIN_CURRENT_P3 = "nh-ad-region-review-input-v9"
PARSER_FIN_PAIRS = {(PARSER_FIN_P1, PARSER_FIN_P3),
                    (PARSER_FIN_CURRENT_P1, PARSER_FIN_CURRENT_P3)}


def adapt_p1_p3(p1: dict[str, Any], p3: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return canonical P1/P3 objects or reject an unsupported pair.

    P1 and P3 are always adapted as one pair.  Accepting only one external
    revision would make line ownership unverifiable and is therefore rejected.
    """
    p1_version = (p1.get("reading_evidence_contract") or p1.get("contract") or {}).get("version")
    p3_version = (p3.get("contract") or {}).get("version")
    if p1_version == CANONICAL_P1 and p3_version == CANONICAL_P3:
        _validate_partition(p1, p3)
        return p1, p3
    if p1_version == EXTERNAL_P1 and p3_version == EXTERNAL_P3:
        return _adapt_external_pair(p1, p3)
    if (p1_version, p3_version) in PARSER_FIN_PAIRS:
        return _adapt_parser_fin_pair(p1, p3)
    raise ValueError(
        "unsupported parser contract pair: "
        f"P1={p1_version!r}, P3={p3_version!r}"
    )


def _adapt_external_pair(source_p1: dict[str, Any], source_p3: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if source_p1.get("doc_id") != (source_p3.get("document") or {}).get("doc_id"):
        raise ValueError("external P1/P3 doc_id mismatch")

    p1 = {
        "doc_id": source_p1.get("doc_id"),
        "source_file": source_p1.get("source_file"),
        "file_type": source_p1.get("file_type"),
        "classification": copy.deepcopy(source_p1.get("classification") or {}),
        "template": copy.deepcopy(source_p1.get("template") or {}),
        "reading_evidence_contract": {
            "version": CANONICAL_P1,
            "parser_primary_text": "pages[].regions[].lines[].parser_text",
            "parser_primary_text_sources": ["digital", "ocr", "hybrid"],
            "vlm_region_reading_mode": "external_parser_observation",
            "parser_mutates_primary_text_from_vlm": False,
            "adapter_source_contract": EXTERNAL_P1,
        },
        "pages": [_adapt_p1_page(page) for page in source_p1.get("pages") or []],
        "notes": copy.deepcopy(source_p1.get("notes") or []),
        "coverage": copy.deepcopy(source_p1.get("coverage") or {}),
        "quality": copy.deepcopy(source_p1.get("quality") or {}),
        "relations": copy.deepcopy(source_p1.get("relations") or []),
        "_adapter_provenance": {
            "adapter": "nh-ad-parser-contract-adapter-v1",
            "source_p1_contract": EXTERNAL_P1,
            "source_p3_contract": EXTERNAL_P3,
            "lossy_fields": [
                "physical page dimensions absent in source", "measured contrast absent in source",
            ],
        },
    }
    p3 = {
        "contract": {
            "version": CANONICAL_P3,
            "source_evidence_version": CANONICAL_P1,
            "review_unit": "region",
            "text_policy": "external P3 selected_text; original P1 preserved",
            "label_policy": "labels retain parser line spans",
        },
        "document": {
            "doc_id": (source_p3.get("document") or {}).get("doc_id"),
            "source_file": (source_p3.get("document") or {}).get("source_file"),
            "file_type": (source_p3.get("document") or {}).get("file_type"),
        },
        "pages": [_adapt_p3_page(page) for page in source_p3.get("pages") or []],
        "unverified_recovery_candidates": copy.deepcopy(source_p3.get("unverified_recovery_candidates") or []),
        "diagnostics": copy.deepcopy(source_p3.get("diagnostics") or {}),
        "summary": copy.deepcopy(source_p3.get("summary") or {}),
    }
    _validate_partition(p1, p3)
    return p1, p3


def _adapt_parser_fin_pair(
    source_p1: dict[str, Any], source_p3: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project explicitly supported nh-parser-fin pairs without inventing geometry.

    P3 v6 intentionally addresses evidence by ``region_id`` and omits line
    references.  The references below are copied from the matching P1 region;
    selected text remains region-level whenever it differs from those lines.
    P1-only unassigned lines are retained as their own canonical evidence so
    the compact P3 projection cannot silently delete source text.
    """
    p3_document = source_p3.get("document") or {}
    source_p1_version = (source_p1.get("reading_evidence_contract") or source_p1.get("contract") or {}).get("version")
    source_p3_version = source_p3["contract"]["version"]
    current = source_p3_version == PARSER_FIN_CURRENT_P3
    if current:
        _validate_parser_fin_current_geometry(source_p1, source_p3)
    if source_p1.get("doc_id") != p3_document.get("doc_id"):
        raise ValueError("nh-parser-fin P1/P3 doc_id mismatch")

    classification = copy.deepcopy(source_p1.get("classification") or {})
    for key in (
        "product_group", "ad_type", "product_name_shown",
        "category_source", "classification_confidence",
    ):
        if source_p1.get(key) is not None and key not in classification:
            classification[key] = copy.deepcopy(source_p1[key])

    pages = [_adapt_parser_fin_p1_page(page) for page in source_p1.get("pages") or []]
    p1_region_index = {
        (page.get("page_no"), str(region.get("region_id"))): region
        for page in pages for region in page.get("regions") or []
    }
    p1_pages = {page.get("page_no"): page for page in pages}
    source_pages = {page.get("page_no"): page for page in source_p1.get("pages") or []}
    p3_pages = []
    for page in source_p3.get("pages") or []:
        page_no = page.get("page_no")
        source_page = source_pages.get(page_no) or {}
        regions = []
        for region in page.get("regions") or []:
            region_id = str(region.get("region_id") or "")
            source_region = p1_region_index.get((page_no, region_id))
            if source_region is None:
                raise ValueError(f"nh-parser-fin P3 unknown region {page_no}/{region_id}")
            refs = [str(line.get("line_ref") or "") for line in source_region.get("lines") or []]
            if any(not ref for ref in refs):
                raise ValueError(f"nh-parser-fin P1 missing line_ref {page_no}/{region_id}")
            regions.append({
                "region_id": region_id,
                "review_text": str(region.get("selected_text") or ""),
                "text_source": region.get("text_source"),
                "line_refs": refs,
                # v6 labels are region-wide parser observations and do not
                # contain source spans.  The operational intake template is
                # authoritative, so do not promote inferred labels to exact
                # line evidence here.
                "labels": [],
                "parser_label_hints": copy.deepcopy(region.get("labels") or []),
                "kind": region.get("kind", "text"),
                "parser_observations": {
                    "product_id": region.get("product_id"),
                    "label_scope": "REGION_HINT_ONLY",
                    "review_reasons": copy.deepcopy(source_region.get("review_reasons") or []),
                    "text_source_detail": source_region.get("text_source"),
                    "layout_observation": copy.deepcopy(source_region.get("layout_observation") or {}),
                    "bbox_source": source_region.get("bbox_source"),
                    "bbox_quality": source_region.get("bbox_quality"),
                    "structured": copy.deepcopy(source_region.get("structured") or {}),
                    "source_line_shape": {
                        "records": len(source_region.get("lines") or []),
                        "multiline_records": sum(
                            len(str(line.get("parser_text") or line.get("text") or "").splitlines()) > 1
                            for line in source_region.get("lines") or []
                        ),
                        "bboxless_records": sum(
                            line.get("bbox") is None for line in source_region.get("lines") or []
                        ),
                        # Character alignment is distinct from proving a
                        # physical rendered line or a notice meaning boundary.
                        "physical_line_verification": "NOT_ATTESTED",
                    },
                    "page_processing_route": (
                        source_page.get("processing_route") or (source_page.get("origin") or {}).get("processing_route")
                        or source_page.get("parse_route")
                    ),
                    "coordinate_surface": (source_page.get("structure_probe") or {}).get("coordinate_surface"),
                    "render_engine": ((source_page.get("origin") or {}).get("render") or {}).get("engine"),
                },
                "text_selection": {
                    "needs_review": bool(region.get("needs_review")),
                    "selection_status": "needs_review" if region.get("needs_review") else "selected",
                    "reason": "; ".join(["nh-parser-fin region evidence verification",
                                          *(str(value) for value in source_region.get("review_reasons") or [])]),
                },
            })
        canonical_page = p1_pages.get(page_no)
        if canonical_page is None:
            raise ValueError(f"nh-parser-fin P3 unknown page {page_no}")
        unassigned = [{
            "line_ref": str(line.get("line_ref") or ""),
            "review_text": str(line.get("parser_text", line.get("text") or "")),
            "text_source": line.get("text_source", line.get("source")),
            "text_selection": {
                "needs_review": False,
                "selection_status": "parser_source",
                "reason": "P1 unassigned source line retained by adapter",
            },
        } for line in canonical_page.get("unassigned_lines") or []]
        p3_pages.append({"page_no": page_no, "regions": regions, "unassigned_text": unassigned})

    p1 = {
        "doc_id": source_p1.get("doc_id"),
        "source_file": source_p1.get("source_file"),
        "file_type": source_p1.get("file_type"),
        "classification": classification,
        "template": copy.deepcopy(source_p1.get("template") or p3_document.get("template") or {}),
        "reading_evidence_contract": {
            "version": CANONICAL_P1,
            "parser_primary_text": "pages[].regions[].lines[].parser_text",
            "parser_primary_text_sources": ["digital", "ocr", "hybrid"],
            "vlm_region_reading_mode": "external_parser_observation",
            "parser_mutates_primary_text_from_vlm": False,
            "adapter_source_contract": source_p1_version,
        },
        "pages": pages,
        "notes": copy.deepcopy(source_p1.get("notes") or []),
        "coverage": copy.deepcopy(source_p1.get("coverage") or {}),
        "quality": copy.deepcopy(source_p1.get("quality") or {}),
        "relations": copy.deepcopy(source_p1.get("relations") or []),
        "_adapter_provenance": {
            "adapter": "nh-parser-fin-contract-adapter-v2",
            "source_p1_contract": source_p1_version,
            "source_p3_contract": source_p3_version,
            "bbox_policy": "P1 OCR/PDF/layout coordinates only; never VLM-generated",
        },
    }
    p3 = {
        "contract": {
            "version": CANONICAL_P3,
            "source_evidence_version": CANONICAL_P1,
            "review_unit": "region",
            "text_policy": "nh-parser-fin P3 selected_text; original P1 preserved",
            "label_policy": "region labels are retrieval hints only; no invented line spans",
        },
        "document": {
            "doc_id": p3_document.get("doc_id"),
            "source_file": p3_document.get("source_file"),
            "file_type": p3_document.get("file_type"),
        },
        "pages": p3_pages,
        "unverified_recovery_candidates": [
            {"page_no": page.get("page_no"), **copy.deepcopy(candidate)}
            for page in source_p1.get("pages") or []
            for candidate in page.get("recovery_candidates") or []
        ],
        "diagnostics": {"review_units": copy.deepcopy(source_p3.get("review_units") or [])},
        "summary": copy.deepcopy(source_p1.get("summary") or {}),
    }
    _validate_partition(p1, p3)
    return p1, p3


def _validate_parser_fin_current_geometry(p1: dict[str, Any], p3: dict[str, Any]) -> None:
    """v9 geometry is a projection of the same P1 page, not a second source."""
    if p3["contract"].get("source_evidence_version") != PARSER_FIN_CURRENT_P1:
        raise ValueError("nh-parser-fin P3 source evidence version mismatch")
    document = p3.get("document") or {}
    if any(p1.get(key) != document.get(key) for key in ("doc_id", "source_file", "file_type")):
        raise ValueError("nh-parser-fin P1/P3 document identity mismatch")
    pages = {page.get("page_no"): page for page in p1.get("pages") or []}
    for page in p3.get("pages") or []:
        number = page.get("page_no")
        source = pages.get(number)
        canvas = page.get("canvas")
        if (type(number) is not int or source is None or canvas != source.get("canvas")
                or not isinstance(canvas, list) or len(canvas) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                       for value in canvas)):
            raise ValueError("nh-parser-fin P1/P3 canvas mismatch or invalid canvas")
        regions = {row.get("region_id"): row for row in source.get("regions") or []}
        for row in page.get("regions") or []:
            region_id = row.get("region_id")
            original = regions.get(region_id)
            bbox = row.get("bbox")
            if (not isinstance(region_id, str) or re.fullmatch(rf"p{number}_r\d{{3,}}", region_id) is None
                    or original is None or bbox != original.get("bbox")
                    or row.get("product_id") != original.get("product_id")):
                raise ValueError("nh-parser-fin P1/P3 region identity, ownership or bbox mismatch")
            if bbox is not None and (
                not isinstance(bbox, list) or len(bbox) != 4
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in bbox)
                or not 0 <= bbox[0] < bbox[2] <= canvas[0]
                or not 0 <= bbox[1] < bbox[3] <= canvas[1]
            ):
                raise ValueError("nh-parser-fin region bbox outside canvas")
            if (row.get("kind") not in {"text", "table"}
                    or row.get("text_source") not in {"hwp", "digital", "ocr", "vlm"}
                    or type(row.get("needs_review")) is not bool
                    or not isinstance(row.get("labels"), list)
                    or any(not isinstance(label, str) for label in row["labels"])):
                raise ValueError("nh-parser-fin invalid v9 region fields")


def _adapt_parser_fin_p1_page(page: dict[str, Any]) -> dict[str, Any]:
    canvas = page.get("canvas") or [page.get("canvas_w"), page.get("canvas_h")]
    canvas_w = canvas[0] if isinstance(canvas, (list, tuple)) and len(canvas) == 2 else None
    canvas_h = canvas[1] if isinstance(canvas, (list, tuple)) and len(canvas) == 2 else None
    regions = []
    for region in page.get("regions") or []:
        value = copy.deepcopy(region)
        observed_layout = region.get("layout_observation") or {}
        value["layout"] = {
            "label": observed_layout.get("label") or region.get("label"),
            "score": observed_layout.get("score", region.get("layout_score")),
            "role": region.get("role"),
        }
        for line in value.get("lines") or []:
            line["parser_text"] = str(line.get("text") or "")
            line["text_source"] = line.get("source")
            line["ocr_confidence"] = line.get("confidence")
        regions.append(value)
    unassigned = copy.deepcopy(page.get("unassigned_lines") or [])
    for line in unassigned:
        line["parser_text"] = str(line.get("text") or "")
        line["text_source"] = line.get("source")
        line["ocr_confidence"] = line.get("confidence")
    return {
        "page_no": page.get("page_no"),
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "dpi": page.get("dpi") or (page.get("origin") or {}).get("dpi_used"),
        "parse_route": (page.get("parse_route") or page.get("processing_route")
                        or (page.get("origin") or {}).get("processing_route")),
        "parse_status": page.get("parse_status"),
        "unread_regions": copy.deepcopy(page.get("unread_regions") or []),
        "relations": copy.deepcopy(page.get("relations") or []),
        "regions": regions,
        "unassigned_lines": unassigned,
        "recovery_candidates": copy.deepcopy(page.get("recovery_candidates") or []),
    }


def _adapt_p1_page(page: dict[str, Any]) -> dict[str, Any]:
    regions = []
    for region in page.get("regions") or []:
        value = copy.deepcopy(region)
        value["layout"] = {
            "label": region.get("label"),
            "score": region.get("layout_score"),
        }
        value["template_labels"] = copy.deepcopy(region.get("template_labels") or [])
        for line in value.get("lines") or []:
            line["parser_text"] = str(line.get("text") or "")
            line["text_source"] = line.get("source")
            line["ocr_confidence"] = line.get("confidence")
        regions.append(value)
    unassigned = copy.deepcopy(page.get("unassigned_lines") or [])
    for line in unassigned:
        line["parser_text"] = str(line.get("text") or "")
        line["text_source"] = line.get("source")
        line["ocr_confidence"] = line.get("confidence")
    return {
        "page_no": page.get("page_no"),
        "canvas_w": page.get("canvas_w"),
        "canvas_h": page.get("canvas_h"),
        "dpi": page.get("dpi"),
        "parse_route": page.get("parse_route"),
        "parse_status": page.get("parse_status"),
        "unread_regions": copy.deepcopy(page.get("unread_regions") or []),
        "relations": copy.deepcopy(page.get("relations") or []),
        **{key: copy.deepcopy(page[key]) for key in ("physical_width_mm", "physical_height_mm") if key in page},
        "regions": regions,
        "unassigned_lines": unassigned,
        "recovery_candidates": copy.deepcopy(page.get("recovery_candidates") or []),
    }


def _adapt_p3_page(page: dict[str, Any]) -> dict[str, Any]:
    regions = []
    for region in page.get("regions") or []:
        regions.append({
            "region_id": region.get("region_id"),
            "review_text": str(region.get("selected_text") or ""),
            "text_source": region.get("selected_source"),
            "line_refs": copy.deepcopy(region.get("line_refs") or []),
            "labels": copy.deepcopy(region.get("labels") or []),
            "text_selection": {
                key: copy.deepcopy(region[key])
                for key in ("selection_status", "needs_review", "confidence", "reason")
                if key in region
            },
        })
    unassigned = []
    for line in page.get("unassigned_text") or []:
        unassigned.append({
            "line_ref": line.get("line_ref"),
            "review_text": str(line.get("selected_text") or ""),
            "text_source": line.get("selected_source"),
            "text_selection": {
                key: copy.deepcopy(line[key])
                for key in ("selection_status", "needs_review", "confidence", "reason")
                if key in line
            },
        })
    return {
        "page_no": page.get("page_no"),
        "regions": regions,
        "unassigned_text": unassigned,
    }


def _validate_partition(p1: dict[str, Any], p3: dict[str, Any]) -> None:
    """Fail closed if translation would lose, duplicate, or reassign a line."""
    def unique_index(rows, key, location):
        index = {}
        for row in rows or []:
            value = row.get(key)
            if value in (None, "") or value in index:
                raise ValueError(f"P1/P3 missing or duplicate {key} at {location}")
            index[value] = row
        return index

    p1_pages = unique_index(p1.get("pages"), "page_no", "P1")
    p3_pages = unique_index(p3.get("pages"), "page_no", "P3")
    if set(p1_pages) != set(p3_pages):
        raise ValueError("external P1/P3 page set mismatch")
    source_refs: list[str] = []
    selected_refs: list[str] = []
    for page_no, page in p1_pages.items():
        p3_page = p3_pages[page_no]
        p1_regions = unique_index(page.get("regions"), "region_id", f"P1 page {page_no}")
        p3_regions = unique_index(p3_page.get("regions"), "region_id", f"P3 page {page_no}")
        if set(p3_regions) - set(p1_regions):
            raise ValueError(f"P3 unknown region on page {page_no}")
        for region_id, region in p1_regions.items():
            refs = [str(line.get("line_ref") or "") for line in region.get("lines") or []]
            projection = p3_regions.get(region_id)
            # Some image pages have a trustworthy layout bbox but no OCR line.
            # P3 may still provide a VLM reading for that exact P1 region.  It
            # remains region-level evidence: it owns no canonical line and must
            # never acquire an invented line bbox.  A text projection without
            # any P1 geometry is still rejected.
            if not refs:
                if projection is not None and projection.get("line_refs"):
                    raise ValueError(
                        f"external P3 assigns line refs to empty P1 region on page {page_no}"
                    )
                if (
                    projection is not None
                    and str(projection.get("review_text") or "").strip()
                    and not region.get("bbox")
                ):
                    raise ValueError(
                        f"external P3 assigns text to geometry-free P1 region on page {page_no}"
                    )
                continue
            if any(not ref for ref in refs):
                raise ValueError(f"external P1 missing line_ref on page {page_no}")
            if projection is None or refs != [str(ref) for ref in projection.get("line_refs") or []]:
                raise ValueError(f"external P1/P3 region line ownership mismatch on page {page_no}")
            source_refs.extend(refs)
            selected_refs.extend(str(ref) for ref in projection.get("line_refs") or [])
        p3_unassigned = unique_index(p3_page.get("unassigned_text"), "line_ref", f"P3 page {page_no}")
        p1_unassigned_refs = []
        for line in page.get("unassigned_lines") or []:
            ref = str(line.get("line_ref") or "")
            if not ref or ref not in p3_unassigned:
                raise ValueError(f"external P3 missing unassigned line on page {page_no}")
            source_refs.append(ref)
            p1_unassigned_refs.append(ref)
        if set(p1_unassigned_refs) != set(p3_unassigned):
            raise ValueError(f"P3 unknown unassigned line on page {page_no}")
        selected_refs.extend(p3_unassigned)
    if len(source_refs) != len(set(source_refs)) or len(selected_refs) != len(set(selected_refs)):
        raise ValueError("external P1/P3 line references are not unique")
    if set(source_refs) != set(selected_refs):
        raise ValueError("external P1/P3 line partition is not exact")
