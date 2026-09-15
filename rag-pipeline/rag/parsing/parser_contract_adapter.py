"""Adapt supported parser P1/P3 revisions to the canonical RAG boundary.

The adapter is deliberately a structural translation only.  It does not infer
product routing, create visibility measurements, change parser text, or merge
regions.  The original parser JSON remains the on-disk audit source; callers
record its hashes before this in-memory projection is consumed.
"""
from __future__ import annotations

import copy
from typing import Any


CANONICAL_P1 = "nh-ad-review-evidence-v6"
CANONICAL_P3 = "nh-ad-review-region-input-v1"
EXTERNAL_P1 = "nh-ad-parse-evidence-v1"
EXTERNAL_P3 = "nh-ad-region-review-input-v1"


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
            # The parser retains layout-only/illustrative regions in P1 but
            # intentionally omits them from the text-focused P3 projection.
            # They own no text and therefore are not part of the line partition.
            if not refs:
                if projection is not None and (
                    projection.get("line_refs")
                    or str(projection.get("review_text") or "").strip()
                ):
                    raise ValueError(
                        f"external P3 assigns text to empty P1 region on page {page_no}"
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
