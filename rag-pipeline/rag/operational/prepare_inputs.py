# -*- coding: utf-8 -*-
"""Combine P1 evidence-v6 and P3 region-input-v1, then build search views.

P1 remains the audit source.  P3 supplies the non-merged region text and label
spans.  The combined JSON is the downstream review contract; Elasticsearch
documents are projections of it, not a second source of truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from rag.operational.contracts import (
    INTEGRATED_INPUT_VERSION,
    SEARCH_DOCUMENT_VERSION,
    validate_integrated_input,
    validate_search_collections,
)
from rag.operational.policy import routing_field


MAX_FINE_CHARS = 700
BULLET_START = re.compile(
    r"(?m)(?=^\s*(?:[•▪◦‣⁃※\uf0a7*-]|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\d+[.)]))"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compact(text: str) -> str:
    return "".join(char for char in str(text or "") if not char.isspace())


def search_text(text: str) -> str:
    """Normalize whitespace only; canonical characters must be unchanged."""
    original = str(text or "")
    value = re.sub(r"\s+", " ", original).strip()
    if compact(value) != compact(original):
        raise ValueError("search normalization changed canonical characters")
    return value


def _label_by_line(region_p3: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for label in region_p3.get("labels") or []:
        base = {"label_id": label.get("label_id"), "label": label.get("label")}
        for span in label.get("spans") or []:
            item = {**base, "sources": span.get("sources") or []}
            if span.get("confidence") is not None:
                item["confidence"] = span["confidence"]
            for ref in span.get("line_refs") or []:
                bucket = result.setdefault(str(ref), [])
                if item not in bucket:
                    bucket.append(item)
    return result


def _minimal_line(line: dict[str, Any], labels: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "line_ref": str(line.get("line_ref") or ""),
        "text": str(line.get("parser_text", line.get("text") or "")),
        "bbox": line.get("bbox"),
        "text_source": line.get("text_source", line.get("source")),
        "confidence": line.get("ocr_confidence", line.get("confidence")),
        "style": line.get("style"),
        "labels": labels,
    }


def combine(p1_path: Path, p3_path: Path) -> dict[str, Any]:
    p1, p3 = read_json(p1_path), read_json(p3_path)
    if (p1.get("reading_evidence_contract") or {}).get("version") != "nh-ad-review-evidence-v6":
        raise ValueError(f"not P1 evidence-v6: {p1_path}")
    if (p3.get("contract") or {}).get("version") != "nh-ad-review-region-input-v1":
        raise ValueError(f"not P3 region-input-v1: {p3_path}")
    if p1.get("doc_id") != (p3.get("document") or {}).get("doc_id"):
        raise ValueError(f"P1/P3 doc_id mismatch: {p1_path.name}")

    p3_pages = {page.get("page_no"): page for page in p3.get("pages") or []}
    p1_page_numbers = [page.get("page_no") for page in p1.get("pages") or []]
    if set(p3_pages) != set(p1_page_numbers):
        raise ValueError(f"P1/P3 page set mismatch: {p1_path.name}")
    pages: list[dict[str, Any]] = []
    source_refs: list[str] = []
    p3_partition_refs: list[str] = []
    for page in p1.get("pages") or []:
        page_no = page.get("page_no")
        p3_page = p3_pages.get(page_no) or {}
        p3_regions = {str(region.get("region_id")): region for region in p3_page.get("regions") or []}
        regions: list[dict[str, Any]] = []
        for region in page.get("regions") or []:
            region_id = str(region.get("region_id") or "")
            lines_raw = region.get("lines") or []
            if not lines_raw:
                continue
            region_p3 = p3_regions.get(region_id)
            if region_p3 is None:
                raise ValueError(f"P3 missing non-empty region {page_no}/{region_id}")
            by_line = _label_by_line(region_p3)
            expected_refs = [str(ref) for ref in region_p3.get("line_refs") or []]
            lines = []
            for line in lines_raw:
                ref = str(line.get("line_ref") or "")
                if not ref:
                    raise ValueError(f"missing line_ref {page_no}/{region_id}")
                source_refs.append(ref)
                lines.append(_minimal_line(line, by_line.get(ref, [])))
            refs = [line["line_ref"] for line in lines]
            p3_partition_refs.extend(expected_refs)
            if refs != expected_refs:
                raise ValueError(f"P1/P3 region line_ref mismatch: {page_no}/{region_id}")
            labels = region_p3.get("labels") or []
            labelled_count = sum(bool(line["labels"]) for line in lines)
            regions.append({
                "evidence_id": f"{p1['doc_id']}#p{page_no}:{region_id}",
                "region_id": region_id,
                "card_no": region.get("card_no"),
                "bbox": region.get("bbox"),
                "layout": region.get("layout"),
                "final_text": str(region_p3.get("review_text") or ""),
                "text_source": region_p3.get("text_source"),
                "line_refs": refs,
                "lines": lines,
                "labels": labels,
                "assignment_status": (
                    "unassigned" if labelled_count == 0
                    else "assigned" if labelled_count == len(lines)
                    else "mixed"
                ),
                "visibility": region.get("visibility"),
                "table": region.get("table"),
            })

        unassigned = []
        p3_unassigned = {str(row.get("line_ref")): row for row in p3_page.get("unassigned_text") or []}
        for line in page.get("unassigned_lines") or []:
            ref = str(line.get("line_ref") or "")
            if not ref or ref not in p3_unassigned:
                raise ValueError(f"P3 missing unassigned line {page_no}/{ref}")
            source_refs.append(ref)
            p3_partition_refs.append(ref)
            unassigned.append(_minimal_line(line, []))
        pages.append({
            "page_no": page_no,
            "canvas_w": page.get("canvas_w"),
            "canvas_h": page.get("canvas_h"),
            "dpi": page.get("dpi"),
            "parse_route": page.get("parse_route"),
            "parse_status": page.get("parse_status"),
            "regions": regions,
            "unassigned_lines": unassigned,
        })

    if (
        len(source_refs) != len(set(source_refs))
        or len(p3_partition_refs) != len(set(p3_partition_refs))
        or source_refs != p3_partition_refs
    ):
        raise ValueError("line partition is not exact")

    classification = p1.get("classification") or {}
    template = p1.get("template") or {}
    result = {
        "contract": {
            "version": INTEGRATED_INPUT_VERSION,
            "sources": {
                "p1_contract": "nh-ad-review-evidence-v6",
                "p3_contract": "nh-ad-review-region-input-v1",
                "p1_sha256": sha256(p1_path),
                "p3_sha256": sha256(p3_path),
            },
            "review_unit": "original parser region; same-label regions are not merged",
            "final_text_policy": "P3 review_text selected from P1 judge policy",
        },
        "document": {
            "ad_id": p1.get("doc_id"),
            "source_file": p1.get("source_file"),
            "file_type": p1.get("file_type"),
            "dataset_group": (p1.get("batch_source") or {}).get("input_group"),
            "input_relative_path": (p1.get("batch_source") or {}).get("relative_path"),
            "routing_metadata": {
                "product_group": classification.get("product_group"),
                "ad_type": classification.get("ad_type"),
                "product_name_shown": classification.get("product_name_shown"),
                "template_id": template.get("template_id"),
                "classification_source": classification.get("source"),
            },
        },
        "pages": pages,
        "unverified_recovery_candidates": p3.get("unverified_recovery_candidates") or [],
        "diagnostics": p3.get("diagnostics") or {},
        "quality": {
            "line_count": len(source_refs),
            "line_partition_exact": True,
            "region_count": sum(len(page["regions"]) for page in pages),
            "empty_region_count": sum(
                not region["final_text"].strip() for page in pages for region in page["regions"]
            ),
        },
    }
    validate_integrated_input(result)
    return result


def _split_parts(line: dict[str, Any]) -> list[dict[str, Any]]:
    text = line["text"]
    if not text:
        return []
    starts = sorted({0, *(match.start() for match in BULLET_START.finditer(text) if match.start() > 0)})
    parts = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        if text[start:end].strip():
            parts.append({"text": text[start:end], "line_ref": line["line_ref"], "char_start": start, "char_end": end})
    return parts


def _fine_views(region: dict[str, Any]) -> list[dict[str, Any]]:
    if region.get("text_source") == "vlm_judge_selected_region_test":
        text = region["final_text"]
        starts = sorted({0, *(match.start() for match in BULLET_START.finditer(text) if match.start() > 0)})
        raw_parts = []
        for idx, start in enumerate(starts):
            end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
            if text[start:end].strip():
                raw_parts.append({
                    "text": text[start:end],
                    "line_ref": None,
                    "char_start": start,
                    "char_end": end,
                })
        parts = raw_parts
        evidence_refs = region["line_refs"]
        span_status = "region_level_vlm_selection"
    else:
        parts = [part for line in region["lines"] for part in _split_parts(line)]
        evidence_refs = None
        span_status = "parser_line_exact"
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for part in parts:
        starts_bullet = bool(BULLET_START.match(part["text"]))
        if current and (starts_bullet or size + len(part["text"]) > MAX_FINE_CHARS):
            groups.append(current)
            current, size = [], 0
        current.append(part)
        size += len(part["text"])
    if current:
        groups.append(current)
    rows = []
    for index, group in enumerate(groups, 1):
        text = "\n".join(part["text"] for part in group)
        refs = evidence_refs or list(dict.fromkeys(part["line_ref"] for part in group))
        rows.append({
            "doc_id": f"{region['evidence_id']}~s{index:03d}",
            "parent_doc_id": region["evidence_id"],
            "view_type": "fine_text",
            "text_canonical": text,
            "text_search": search_text(text),
            "line_refs": refs,
            "span_status": span_status,
            "line_spans": [
                {"line_ref": part["line_ref"], "char_start": part["char_start"], "char_end": part["char_end"]}
                for part in group
            ] if span_status == "parser_line_exact" else [],
        })
    if compact("".join(row["text_canonical"] for row in rows)) != compact(region["final_text"]):
        raise ValueError(f"fine views lost characters: {region['evidence_id']}")
    return rows


def search_docs(ad: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    coarse, fine = [], []
    meta = ad["document"]
    source = meta["routing_metadata"].get("classification_source")
    routing_metadata = {
        "product_group": routing_field(
            meta["routing_metadata"].get("product_group"), default_source=source
        ),
        "ad_type": routing_field(
            meta["routing_metadata"].get("ad_type"), default_source=source
        ),
        "product_name_shown": routing_field(
            meta["routing_metadata"].get("product_name_shown"), default_source=source
        ),
        "template_id": routing_field(
            meta["routing_metadata"].get("template_id"),
            default_source="parser_template",
        ),
        "product_subtype": routing_field(
            meta["routing_metadata"].get("product_subtype"), default_source=source
        ),
        "media_type": routing_field(
            meta["routing_metadata"].get("media_type"), default_source=source
        ),
    }
    for page in ad["pages"]:
        for region in page["regions"]:
            if not region["final_text"].strip():
                continue
            base = {
                "schema_version": SEARCH_DOCUMENT_VERSION,
                "ad_id": meta["ad_id"],
                "source_file": meta["source_file"],
                "routing": meta["routing_metadata"],
                "routing_metadata": routing_metadata,
                "page_no": page["page_no"],
                "region_id": region["region_id"],
                "bbox": region["bbox"],
                "labels": region["labels"],
                "assignment_status": region["assignment_status"],
            }
            coarse.append({
                **base,
                "doc_id": region["evidence_id"],
                "parent_doc_id": None,
                "parent_chunk_id": None,
                "view_type": "canonical_region",
                "text_canonical": region["final_text"],
                "text_search": search_text(region["final_text"]),
                "line_refs": region["line_refs"],
            })
            line_labels = {line["line_ref"]: line["labels"] for line in region["lines"]}
            for view in _fine_views(region):
                labels = []
                for ref in view["line_refs"]:
                    for label in line_labels.get(ref, []):
                        if label not in labels:
                            labels.append(label)
                fine.append({
                    **base,
                    **view,
                    "parent_chunk_id": view["parent_doc_id"],
                    "labels": labels,
                })
    return coarse, fine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    p1_files = sorted(args.batch_root.rglob("json/*.json"))
    if not p1_files:
        raise SystemExit(f"no P1 files under {args.batch_root}")
    all_coarse, all_fine = [], []
    docs = []
    for p1_path in p1_files:
        p3_path = p1_path.parent.parent / "review_region_input" / p1_path.name
        if not p3_path.is_file():
            raise ValueError(f"missing P3 pair: {p3_path}")
        ad = combine(p1_path, p3_path)
        target = args.out / "integrated" / p1_path.name
        write_json(target, ad)
        coarse, fine = search_docs(ad)
        all_coarse.extend(coarse)
        all_fine.extend(fine)
        docs.append({
            "ad_id": ad["document"]["ad_id"],
            "source_file": ad["document"]["source_file"],
            "p1": str(p1_path.resolve()),
            "p3": str(p3_path.resolve()),
            "integrated": str(target.resolve()),
            "regions": len(coarse),
            "fine_views": len(fine),
        })
    write_jsonl(args.out / "evidence_coarse.jsonl", all_coarse)
    write_jsonl(args.out / "evidence_fine.jsonl", all_fine)
    validate_search_collections(
        [read_json(args.out / "integrated" / path.name) for path in p1_files],
        all_coarse,
        all_fine,
    )
    write_json(args.out / "manifest.json", {
        "schema_version": "p1-p3-search-build-v1",
        "documents": docs,
        "counts": {"ads": len(docs), "coarse": len(all_coarse), "fine": len(all_fine)},
        "checks": {
            "p1_p3_identity": "pass",
            "same_label_regions_not_merged": "pass",
            "line_partition_exact": "pass",
            "fine_character_coverage": "pass",
        },
    })
    print(json.dumps({"out": str(args.out), "ads": len(docs), "coarse": len(all_coarse), "fine": len(all_fine)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
