# -*- coding: utf-8 -*-
"""Combine P1 evidence-v6 and P3 region-input-v1, then build search views.

P1 remains the audit source.  P3 supplies the non-merged region text and label
spans.  The combined JSON is the downstream review contract; Elasticsearch
documents are projections of it, not a second source of truth.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from rag.contracts.validation import (
    INTEGRATED_INPUT_VERSION,
    SEARCH_DOCUMENT_VERSION,
    validate_integrated_input,
    validate_search_collections,
)
from rag.judgment.policy import routing_field
from rag.parsing.parser_contract_adapter import adapt_p1_p3


# A packing target, not a hard split point. An atomic parser line or visual
# table row may exceed it because cutting an unverified semantic unit merely
# to satisfy a length limit can separate a condition from its obligation.
TARGET_FINE_CHARS = 700
# ``\d+[.)]``는 번호 매기기 말머리를 뜻한다. 뒤에 숫자가 이어지면 그것은
# 말머리가 아니라 소수(0.7)나 날짜(2026.6.22.)이므로 자르지 않는다.
BULLET_START = re.compile(
    r"(?m)(?=^\s*(?:[•▪◦‣⁃※\uf0a7*-]|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\d+[.)](?!\d)))"
)

# 표 영역은 라벨 셀과 값 셀이 서로 다른 파서 라인으로 나온다. 두 라인의 세로
# 구간이 이만큼 겹치면 같은 시각적 행으로 본다.
ROW_OVERLAP_RATIO = 0.5
PAGE_CHROME_LAYOUTS = {
    "header", "footer", "page_header", "page_footer", "navigation", "nav", "menu"
}


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


def source_role(region: dict[str, Any]) -> tuple[str, str]:
    """Preserve parser structure as evidence scope, without guessing semantics.

    Explicit header/footer/navigation layout is shared page chrome. Everything
    else remains advertisement content; text keywords never assign this role.
    """
    layout = region.get("layout") or {}
    label = str(layout.get("label") or "").strip().lower()
    if label in PAGE_CHROME_LAYOUTS:
        return "PAGE_CHROME", f"parser_layout:{label}"
    return "ADVERTISEMENT_CONTENT", "parser_layout:content_or_unclassified"


def page_source_roles(page: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Return the parser-declared source role of every region on one page.

    Position is not a role.  A full-page web capture places the product hero
    banner inside the top fifth of the image and the mandatory disclosures
    just above the menu, so an edge-zone rule demotes the product name, the
    principal-loss notice and the compliance approval line to page chrome and
    removes them from body-rule evidence.  Only an explicit parser layout
    label assigns this role; generic navigation wording is rejected after
    judgment by ``rag.judgment.source_checks`` instead.
    """
    return {str(region.get("region_id")): source_role(region)
            for region in page.get("regions") or []}


def parser_classification_field(
    classification: dict[str, Any], field_name: str
) -> dict[str, Any]:
    """Parser confidence never grants the authority of confirmed intake."""
    value = classification.get(field_name)
    source = str(classification.get("source") or "parser_classification")
    confidence = classification.get("confidence")
    return {
        "value": value,
        "source": f"parser_classification:{source}",
        "status": "inferred" if value not in (None, "") else "unknown",
        "confidence": confidence,
    }


def parser_template_field(template: dict[str, Any]) -> dict[str, Any]:
    """Keep the parser's template decision as an observation, not intake."""
    value = template.get("template_id")
    parser_status = str(template.get("status") or "")
    return {
        "value": value,
        "source": "parser_template",
        "status": "inferred" if value not in (None, "") else "unknown",
        "parser_status": parser_status,
    }


def _validated_labels(region_p3: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Keep only spans owned by this region; never repair a label's evidence."""
    refs = region_p3.get("line_refs") or []
    positions = {ref: i for i, ref in enumerate(refs)}
    labels = []
    rejected = False
    for label in region_p3.get("labels") or []:
        spans = []
        for span in label.get("spans") or []:
            selected = span.get("line_refs")
            if (not isinstance(selected, list) or not selected
                    or any(not isinstance(ref, str) or ref not in positions for ref in selected)
                    or any(positions[a] >= positions[b] for a, b in zip(selected, selected[1:]))):
                rejected = True
                continue
            if "line_from" in span or "line_to" in span:
                start, end = span.get("line_from"), span.get("line_to")
                if (type(start) is not int or type(end) is not int
                        or not 0 <= start <= end < len(refs)
                        or selected != refs[start:end + 1]):
                    rejected = True
                    continue
            spans.append(copy.deepcopy(span))
        if spans:
            labels.append({**copy.deepcopy(label), "spans": spans})
    return labels, rejected


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
    p1, p3 = adapt_p1_p3(p1, p3)
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
            region_p3 = p3_regions.get(region_id)
            if not lines_raw and region_p3 is None:
                # A layout-only/illustrative region carries no searchable text.
                continue
            if region_p3 is None:
                raise ValueError(f"P3 missing non-empty region {page_no}/{region_id}")
            if (
                not lines_raw
                and not str(region_p3.get("review_text") or "").strip()
            ):
                continue
            if not lines_raw and not region.get("bbox"):
                raise ValueError(f"P3 text has no P1 region bbox: {page_no}/{region_id}")
            labels, rejected_spans = _validated_labels(region_p3)
            by_line = _label_by_line({"labels": labels})
            selection = copy.deepcopy(region_p3.get("text_selection") or {})
            if rejected_spans:
                selection["needs_review"] = True
                selection["reason"] = (
                    str(selection.get("reason") or "") + "; label_source_span_invalid"
                ).lstrip("; ")
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
            labelled_count = sum(bool(line["labels"]) for line in lines)
            regions.append({
                "evidence_id": f"{p1['doc_id']}#p{page_no}:{region_id}",
                "region_id": region_id,
                "card_no": region.get("card_no"),
                "bbox": region.get("bbox"),
                "layout": region.get("layout"),
                "final_text": str(region_p3.get("review_text") or ""),
                "text_source": region_p3.get("text_source"),
                "text_selection": selection,
                "line_refs": refs,
                "lines": lines,
                "labels": labels,
                "parser_label_hints": copy.deepcopy(region_p3.get("parser_label_hints") or []),
                "kind": region_p3.get("kind", "table" if region.get("table") else "text"),
                "parser_observations": copy.deepcopy(region_p3.get("parser_observations") or {}),
                "assignment_status": (
                    "unassigned" if not lines
                    else
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
            projected_line = _minimal_line(line, [])
            projected_line["text_selection"] = copy.deepcopy(p3_unassigned[ref].get("text_selection") or {})
            unassigned.append(projected_line)
        pages.append({
            "page_no": page_no,
            "canvas_w": page.get("canvas_w"),
            "canvas_h": page.get("canvas_h"),
            "dpi": page.get("dpi"),
            "physical_width_mm": page.get("physical_width_mm"),
            "physical_height_mm": page.get("physical_height_mm"),
            "parse_route": page.get("parse_route"),
            "parse_status": page.get("parse_status"),
            "unread_regions": copy.deepcopy(page.get("unread_regions") or []),
            "relations": copy.deepcopy(page.get("relations") or []),
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
                "product_group": parser_classification_field(classification, "product_group"),
                "ad_type": parser_classification_field(classification, "ad_type"),
                "product_name_shown": parser_classification_field(
                    classification, "product_name_shown"
                ),
                "template_id": parser_template_field(template),
                "classification_source": classification.get("source"),
                "classification_observation": classification,
                "template_observation": template,
            },
        },
        "pages": pages,
        "relations": copy.deepcopy(p1.get("relations") or []),
        "unverified_recovery_candidates": p3.get("unverified_recovery_candidates") or [],
        "diagnostics": {
            **(p3.get("diagnostics") or {}),
            **({"parser_contract_adapter": p1["_adapter_provenance"]}
               if p1.get("_adapter_provenance") else {}),
        },
        "quality": {
            **copy.deepcopy(p1.get("quality") or {}),
            **({"complete_document_read": False if (p1.get("quality") or {}).get("complete_document_read") is False
               else p1["coverage"]["complete_document_read"]}
               if "complete_document_read" in (p1.get("coverage") or {}) else {}),
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


def _split_parts(
    line: dict[str, Any], *, split_bullets: bool = True
) -> list[dict[str, Any]]:
    text = line["text"]
    if not text:
        return []
    starts = (
        sorted({0, *(match.start() for match in BULLET_START.finditer(text) if match.start() > 0)})
        if split_bullets else [0]
    )
    if split_bullets and len(text) > TARGET_FINE_CHARS:
        # A logical source block may contain many newline-delimited paragraphs
        # under one bbox. Split search text at those *source* boundaries while
        # retaining the original line ID, character offsets and block bbox.
        # These offsets do not manufacture physical rendered lines. Never cut
        # an atomic table row or invent boundaries inside an unbroken sentence.
        starts = sorted({*starts, *(match.end() for match in re.finditer(r"\r?\n", text)
                                   if match.end() < len(text))})
    parts = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        if text[start:end].strip():
            parts.append({"text": text[start:end], "line_ref": line["line_ref"],
                          "char_start": start, "char_end": end, "bbox": line.get("bbox")})
    return parts


def _is_table_region(region: dict[str, Any]) -> bool:
    label = str(((region.get("layout") or {}).get("label") or "")).lower()
    return region.get("kind") == "table" or bool(region.get("table")) or "table" in label


def _same_visual_row(previous: Any, current: Any) -> bool:
    """두 파서 라인이 한 표 행에 속하는지 세로 겹침으로 본다."""
    if not (isinstance(previous, (list, tuple)) and isinstance(current, (list, tuple))):
        return False
    if len(previous) < 4 or len(current) < 4:
        return False
    top, bottom = max(previous[1], current[1]), min(previous[3], current[3])
    overlap = bottom - top
    if overlap <= 0:
        return False
    shortest = min(previous[3] - previous[1], current[3] - current[1])
    return shortest > 0 and overlap >= ROW_OVERLAP_RATIO * shortest


def _template_label_names_by_line(region: dict[str, Any]) -> dict[str, set[str]]:
    """파서가 라인에 붙인 템플릿 항목 라벨을 줄 참조별로 모은다.

    파일 병합 후에는 라벨과 원문 모두 자산 접두어를 가진다. 전체 참조를 우선하고,
    접두어 없는 구형 라벨만 현재 영역의 유일한 원문 참조로 대응한다.
    """
    mapping: dict[str, set[str]] = {}
    owned_refs = {str(line.get("line_ref") or "") for line in region.get("lines") or []}
    legacy_refs: dict[str, list[str]] = {}
    for ref in owned_refs:
        legacy_refs.setdefault(ref.split("::", 1)[-1], []).append(ref)
    for label in region.get("labels") or []:
        name = str(label.get("label") or "").strip()
        if not name:
            continue
        for span in label.get("spans") or []:
            for line_ref in span.get("line_refs") or []:
                ref = str(line_ref)
                if ref not in owned_refs:
                    matches = legacy_refs.get(ref, []) if "::" not in ref else []
                    if len(matches) != 1:
                        continue
                    ref = matches[0]
                mapping.setdefault(ref, set()).add(name)
    return mapping


def _unit_label(
    unit: list[dict[str, Any]], label_by_line: dict[str, set[str]]
) -> str | None:
    """한 묶음이 단일 항목에 속할 때만 그 항목 이름을 돌려준다."""
    names: set[str] = set()
    for part in unit:
        names |= label_by_line.get(str(part.get("line_ref") or ""), set())
    return next(iter(names)) if len(names) == 1 else None


def _label_groups(
    rows: list[list[dict[str, Any]]], *, region: dict[str, Any]
) -> list[list[dict[str, Any]]] | None:
    """표의 행을 파서 라벨 경계로 묶는다. 라벨이 없으면 ``None``.

    라벨이 붙지 않은 행은 직전 항목에 딸린 내용으로 보고 이어 붙인다. 주석이
    본문 뒤에 오는 표에서 주석만 떨어져 나가지 않게 하려는 것이다.
    """
    label_by_line = _template_label_names_by_line(region)
    # 라벨이 서로 다른 항목을 둘 이상 구분해 줄 때만 경계로 쓴다. 한 종류뿐이면
    # 표 전체가 한 덩어리가 되어 좌표 방식보다 거칠어진다.
    distinct = {name for names in label_by_line.values() for name in names}
    if len(distinct) < 2:
        return None
    groups: list[list[dict[str, Any]]] = []
    current_label: str | None = None
    for row in rows:
        name = _unit_label(row, label_by_line)
        if not groups or (name is not None and current_label is not None
                          and name != current_label):
            groups.append(list(row))
            current_label = name
        else:
            groups[-1].extend(row)
            if name is not None and current_label is None:
                current_label = name
    return groups


def _row_start_x(row: list[dict[str, Any]]) -> float | None:
    xs = [
        part["bbox"][0]
        for part in row
        if isinstance(part.get("bbox"), (list, tuple)) and len(part["bbox"]) >= 4
    ]
    return min(xs) if xs else None


def _field_groups(
    rows: list[list[dict[str, Any]]], *, region: dict[str, Any]
) -> list[list[dict[str, Any]]]:
    """표의 행들을 항목 단위로 묶는다.

    왼쪽 라벨 열에서 시작하는 행이 새 항목이고, 그보다 들여쓴 행은 그 항목에
    딸린 내용이다. 라벨 열 위치는 이 표 안에서 가장 왼쪽 행 시작점으로 잡는다.
    좌표를 모르면 행 하나를 그대로 항목으로 둔다.
    """
    starts = [_row_start_x(row) for row in rows]
    known = [x for x in starts if x is not None]
    if not known:
        return [list(row) for row in rows]
    label_x = min(known)
    bbox = region.get("bbox")
    width = (
        bbox[2] - bbox[0]
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4 else 0
    )
    tolerance = max(8.0, 0.02 * width)
    groups: list[list[dict[str, Any]]] = []
    for row, start in zip(rows, starts):
        if not groups or (start is not None and start - label_x <= tolerance):
            groups.append(list(row))
        else:
            groups[-1].extend(row)
    return groups


def _split_oversized(
    groups: list[list[dict[str, Any]]], rows_by_group: list[list[list[dict[str, Any]]]]
) -> list[list[dict[str, Any]]]:
    """항목 하나가 상한을 넘으면 행 경계에서만 나눈다."""
    output: list[list[dict[str, Any]]] = []
    for group, rows in zip(groups, rows_by_group):
        if sum(len(part["text"]) for part in group) <= TARGET_FINE_CHARS:
            output.append(group)
            continue
        current: list[dict[str, Any]] = []
        size = 0
        for row in rows:
            row_size = sum(len(part["text"]) for part in row)
            if current and size + row_size > TARGET_FINE_CHARS:
                output.append(current)
                current, size = [], 0
            current.extend(row)
            size += row_size
        if current:
            output.append(current)
    return output


def _atomic_groups(
    parts: list[dict[str, Any]], *, table: bool
) -> list[list[dict[str, Any]]]:
    """청킹이 절대 쪼개면 안 되는 최소 묶음을 만든다.

    표가 아니면 파서 라인 하나가 최소 묶음이라 종전과 같다. 표이면 같은
    시각적 행의 라인들을 한 묶음으로 두어 라벨과 값이 갈리지 않게 한다.
    """
    if not table:
        return [[part] for part in parts]
    groups: list[list[dict[str, Any]]] = []
    for part in parts:
        if groups and _same_visual_row(groups[-1][-1].get("bbox"), part.get("bbox")):
            groups[-1].append(part)
        else:
            groups.append([part])
    return groups


def _selected_text_line_refs(region: dict[str, Any]) -> list[str] | None:
    """Align P3 selected text to the P1 lines which actually contain it.

    A visual parser region can cover most of a page while P3 selects only a
    navigation row or a disclosure inside it.  Returning every region line as
    provenance makes the UI highlight unrelated server headers and lets the
    model cite text it never received.  Use a monotonic exact-text alignment;
    if it cannot be proved, retain the conservative region-level provenance.
    """
    target = compact(str(region.get("final_text") or ""))
    if not target:
        return None
    # Keep at most two paths per matched prefix: two complete matches already
    # prove ambiguity. A greedy first match can wrongly assign a repeated
    # heading/amount to whichever identical line happens to appear first.
    paths: dict[int, list[tuple[str, ...]]] = {0: [()]}
    matches: list[tuple[str, ...]] = []
    for line in region.get("lines") or []:
        value = compact(str(line.get("text") or ""))
        if not value:
            continue
        next_paths = {offset: list(choices) for offset, choices in paths.items()}
        for offset, choices in paths.items():
            if not target.startswith(value, offset):
                continue
            end = offset + len(value)
            for refs in choices:
                candidate = (*refs, str(line["line_ref"]))
                if end == len(target):
                    if candidate not in matches:
                        matches.append(candidate)
                    if len(matches) > 1:
                        return None
                else:
                    bucket = next_paths.setdefault(end, [])
                    if len(bucket) < 2 and candidate not in bucket:
                        bucket.append(candidate)
        paths = next_paths
    return list(matches[0]) if matches else None


def _single_line_agreement_refs(
    region: dict[str, Any], selected_text: str
) -> list[str] | None:
    """Return one parser line which independently agrees with a P3 sentence.

    OCR often omits only the final sentence stop while the VLM-selected text
    retains it.  That harmless difference must not make an exact disclosure
    inherit uncertainty caused by corrections on other lines in a large
    region.  Keep this deliberately narrow: one complete source line, a
    unique match, and whitespace/final-stop differences only.
    """
    target = compact(selected_text).rstrip(".。").strip()
    if not target:
        return None
    matches = [
        str(line["line_ref"])
        for line in region.get("lines") or []
        if compact(str(line.get("text") or "")).rstrip(".。").strip() == target
    ]
    return matches if len(matches) == 1 else None


def _fine_selection(
    region: dict[str, Any], view: dict[str, Any], aligned: bool
) -> dict[str, Any]:
    """Project region reading quality to the exact fine-text span.

    A region-level VLM review flag remains conservative by default.  It may be
    cleared for one fine view only when the VLM judge reported full confidence
    and the selected sentence independently agrees with one unique OCR line.
    Corrections on every other line remain review-required.
    """
    selection = _selection_for_alignment(region, aligned)
    if not aligned or selection.get("needs_review") is False:
        return selection
    if (
        selection.get("selection_status") != "judge_selected_vlm_requires_review"
        or selection.get("confidence") != 1.0
    ):
        return selection
    refs = view.get("line_refs") or []
    agreed = _single_line_agreement_refs(region, str(view.get("text_canonical") or ""))
    if agreed != refs:
        return selection
    selection.update(
        selection_status="independent_line_agreement",
        needs_review=False,
        reason=(
            str(selection.get("reason") or "")
            + "; 해당 세부 문장은 P3 선택문과 P1 OCR 단일 줄이 독립 일치"
        ).lstrip("; "),
    )
    return selection


def _fine_views(region: dict[str, Any]) -> list[dict[str, Any]]:
    is_table = _is_table_region(region)
    selected_refs = _selected_text_line_refs(region)
    exact_original = compact("".join(str(line.get("text") or "") for line in region["lines"])) == compact(region["final_text"])
    # When P3 selects a unique subset of whole P1 lines, keep their real
    # coordinates, character spans and table rows instead of losing them in
    # the region-text fallback. Omitted lines must not label every fine view.
    selected_lines = [line for line in region["lines"] if line["line_ref"] in selected_refs] if selected_refs else region["lines"]
    line_parts = [
        part
        for line in selected_lines
        for part in _split_parts(line, split_bullets=not is_table)
    ]
    line_text = "".join(part["text"] for part in line_parts)
    if compact(line_text) != compact(region["final_text"]):
        # P3 may select region-level OCR/VLM text that deliberately drops a
        # parser artifact or otherwise differs from the P1 line sequence. In
        # that case line-exact character spans would be false provenance, so
        # split the selected canonical text itself while retaining all source
        # line references as region-level evidence.
        text = region["final_text"]
        raw_parts = _split_parts({"text": text, "line_ref": None}, split_bullets=not is_table)
        parts = raw_parts
        evidence_refs = selected_refs or region["line_refs"]
        span_status = (
            "selected_text_line_aligned" if selected_refs
            else "region_level_selected_text"
        )
    else:
        parts = line_parts
        evidence_refs = None
        span_status = "parser_line_exact" if exact_original else "selected_text_line_aligned"
    if parts is not line_parts:
        # 선택 텍스트를 직접 쪼갠 경로에는 라인 bbox가 없어 행 복원이 불가능하다.
        is_table = False
    units = _atomic_groups(parts, table=is_table)
    if is_table:
        # 표는 항목 하나가 한 청크다. 인접 항목을 상한까지 이어붙이면 서로 다른
        # 항목의 수치가 한 창에 섞여 산술 검산이 어긋난다.
        rows_by_group: list[list[list[dict[str, Any]]]] = []
        groups = _label_groups(units, region=region)
        if groups is None:
            groups = _field_groups(units, region=region)
        index = 0
        for group in groups:
            taken: list[list[dict[str, Any]]] = []
            covered = 0
            while index < len(units) and covered < len(group):
                taken.append(units[index])
                covered += len(units[index])
                index += 1
            rows_by_group.append(taken)
        groups = _split_oversized(groups, rows_by_group)
    else:
        groups = []
        current: list[dict[str, Any]] = []
        size = 0
        for unit in units:
            starts_bullet = bool(BULLET_START.match(unit[0]["text"]))
            unit_size = sum(len(part["text"]) for part in unit)
            if current and (starts_bullet or size + unit_size > TARGET_FINE_CHARS):
                groups.append(current)
                current, size = [], 0
            current.extend(unit)
            size += unit_size
        if current:
            groups.append(current)
    rows = []
    for index, group in enumerate(groups, 1):
        text = "\n".join(part["text"] for part in group)
        refs = (
            evidence_refs
            if evidence_refs is not None
            else list(dict.fromkeys(
                part["line_ref"] for part in group if part.get("line_ref")
            ))
        )
        view_span_status = span_status
        if span_status == "region_level_selected_text":
            # A correction elsewhere in the region must not prevent proving
            # the exact source of an unchanged fine view. Never fuzzy-match.
            aligned = _selected_text_line_refs({**region, "final_text": text})
            if not aligned:
                aligned = _single_line_agreement_refs(region, text)
            if aligned:
                refs = aligned
                view_span_status = "selected_text_line_aligned"
        rows.append({
            "doc_id": f"{region['evidence_id']}~s{index:03d}",
            "parent_doc_id": region["evidence_id"],
            "view_type": "fine_text",
            "text_canonical": text,
            "text_search": search_text(text),
            "line_refs": refs,
            "span_status": view_span_status,
            "line_spans": [
                {"line_ref": part["line_ref"], "char_start": part["char_start"], "char_end": part["char_end"]}
                for part in group
            ] if parts is line_parts else [],
        })
    if compact("".join(row["text_canonical"] for row in rows)) != compact(region["final_text"]):
        raise ValueError(f"fine views lost characters: {region['evidence_id']}")
    return rows


def _labels_for_refs(region: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    labels = []
    for line in region["lines"]:
        if line["line_ref"] in refs:
            for label in line.get("labels") or []:
                if label not in labels:
                    labels.append(copy.deepcopy(label))
    return labels


def _selection_for_alignment(region: dict[str, Any], aligned: bool) -> dict[str, Any]:
    selection = copy.deepcopy(region.get("text_selection") or {})
    if not aligned:
        selection["needs_review"] = True
        selection["reason"] = (str(selection.get("reason") or "") + "; P3 선택 문장과 P1 원문 줄의 정확한 대응 확인 필요").lstrip("; ")
    return selection


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
        "review_stage": routing_field(
            meta["routing_metadata"].get("review_stage"), default_source=source
        ),
        "association_pre_review": routing_field(
            meta["routing_metadata"].get("association_pre_review"), default_source=source
        ),
        "external_evidence_available": routing_field(
            meta["routing_metadata"].get("external_evidence_available"),
            default_source=source,
        ),
    }
    for page in ad["pages"]:
        page_roles = page_source_roles(page)
        # Unassigned canonical lines still belong to this advertisement. Give
        # each a search projection without inventing a parser region or label.
        unassigned_views = [
            {
                "evidence_id": f"{meta['ad_id']}#unassigned:{line['line_ref']}",
                "region_id": None,
                "bbox": line.get("bbox"),
                "final_text": line["text"],
                "lines": [line],
                "line_refs": [line["line_ref"]],
                "labels": [],
                "assignment_status": "unassigned",
                "text_selection": copy.deepcopy(line.get("text_selection") or {}),
            }
            for line in page.get("unassigned_lines") or []
            if str(line.get("text") or "").strip()
        ]
        for region in [*page["regions"], *unassigned_views]:
            if not region["final_text"].strip():
                continue
            evidence_role, role_basis = page_roles.get(
                str(region.get("region_id")), source_role(region)
            )
            base = {
                "schema_version": SEARCH_DOCUMENT_VERSION,
                "ad_id": meta["ad_id"],
                "product_id": meta.get("product_id"),
                "source_file": page.get("source_file") or meta["source_file"],
                "asset_id": page.get("asset_id"),
                "source_page_no": page.get("source_page_no", page["page_no"]),
                "table": copy.deepcopy(region.get("table")),
                "routing": meta["routing_metadata"],
                "routing_metadata": routing_metadata,
                "page_no": page["page_no"],
                "region_id": region["region_id"],
                "bbox": region["bbox"],
                "layout": copy.deepcopy(region.get("layout")),
                "source_role": evidence_role,
                "source_role_basis": role_basis,
                "labels": region["labels"],
                "parser_label_hints": copy.deepcopy(region.get("parser_label_hints") or []),
                "kind": region.get("kind", "text"),
                "parser_observations": copy.deepcopy(region.get("parser_observations") or {}),
                "text_source": region.get("text_source"),
                "assignment_status": region["assignment_status"],
                "text_selection": copy.deepcopy(region.get("text_selection") or {}),
            }
            line_bbox_by_ref = {
                line["line_ref"]: line.get("bbox")
                for line in region["lines"]
                if line.get("bbox") is not None
            }
            selected_refs = _selected_text_line_refs(region)
            coarse_refs = selected_refs or region["line_refs"]
            line_text_by_ref = {line["line_ref"]: line["text"] for line in region["lines"]}
            coarse.append({
                **base,
                "doc_id": region["evidence_id"],
                "parent_doc_id": None,
                "parent_chunk_id": None,
                "view_type": "canonical_region",
                "text_canonical": region["final_text"],
                "text_search": search_text(region["final_text"]),
                "span_status": "selected_text_line_aligned" if selected_refs else "region_level_selected_text",
                "labels": _labels_for_refs(region, selected_refs) if selected_refs else [],
                "text_selection": _selection_for_alignment(region, bool(selected_refs)),
                "line_refs": coarse_refs,
                "line_texts": {ref: line_text_by_ref[ref] for ref in coarse_refs if ref in line_text_by_ref},
                "line_bboxes": {
                    ref: line_bbox_by_ref[ref]
                    for ref in coarse_refs if ref in line_bbox_by_ref
                },
            })
            for view in _fine_views(region):
                aligned = view["span_status"] != "region_level_selected_text"
                labels = _labels_for_refs(region, view["line_refs"]) if aligned else []
                fine.append({
                    **base,
                    **view,
                    "parent_chunk_id": view["parent_doc_id"],
                    "labels": labels,
                    "text_selection": _fine_selection(region, view, aligned),
                    "line_texts": {
                        ref: line_text_by_ref[ref]
                        for ref in view["line_refs"] if ref in line_text_by_ref
                    },
                    "line_bboxes": {
                        ref: line_bbox_by_ref[ref]
                        for ref in view["line_refs"] if ref in line_bbox_by_ref
                    },
                })
    from rag.parsing.source_structure import table_relations
    relations = [*(relation for page in ad["pages"] for region in page.get("regions") or []
                   for relation in table_relations(region.get("table"))),
                 *(ad.get("relations") or []),
                 *(relation for page in ad["pages"] for relation in page.get("relations") or [])]
    for relation in relations:
        if not isinstance(relation, dict) or any(
            not isinstance(relation.get(key), list)
            or not all(isinstance(ref, str) and ref for ref in relation[key])
            for key in ("from_line_ids", "to_line_ids")
        ):
            raise ValueError("source relation must contain from_line_ids/to_line_ids string arrays")
    for row in [*coarse, *fine]:
        refs = set(row.get("line_refs") or [])
        linked = [copy.deepcopy(relation) for relation in relations
            if isinstance(relation, dict) and refs.intersection(
                [*(relation.get("from_line_ids") or []), *(relation.get("to_line_ids") or [])])]
        if linked:
            row["source_relations"] = linked
    return coarse, fine


def product_scoped_documents(ad: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn one multi-product advertisement into isolated judgment scopes.

    Shared regions are copied into every product scope. Product-specific
    regions appear only in their own scope. The source advertisement ID and
    product identity stay explicit so downstream results can be regrouped
    without using filenames or model inference.
    """
    validate_integrated_input(ad)
    document = ad["document"]
    products = document.get("products") or []
    if not products:
        return [ad]
    if len(products) > 1 and ad.get("unverified_recovery_candidates"):
        raise ValueError(
            "multi-product input has unverified recovery candidates; "
            "assign them before product-scoped judgment"
        )

    source_ad_id = str(document["ad_id"])
    shared = set(document.get("shared_evidence_ids") or [])
    scoped: list[dict[str, Any]] = []
    single_product = len(products) == 1
    for product in products:
        product_id = str(product["product_id"])
        allowed = shared.union(map(str, product.get("evidence_ids") or []))
        value = copy.deepcopy(ad)
        scoped_document = value["document"]
        scoped_document.pop("products", None)
        scoped_document.pop("shared_evidence_ids", None)
        scoped_document["parent_ad_id"] = source_ad_id
        scoped_document["product_id"] = product_id
        scoped_document["product_name"] = str(product["product_name"])
        suffix = hashlib.sha256(product_id.encode("utf-8")).hexdigest()[:12]
        scoped_document["ad_id"] = f"{source_ad_id}::product:{suffix}"
        scope_prefix = scoped_document["ad_id"]
        scoped_document["routing_metadata"] = {
            **copy.deepcopy(document.get("routing_metadata") or {}),
            **copy.deepcopy(product.get("routing_metadata") or {}),
        }

        region_count = 0
        line_count = 0
        empty_region_count = 0
        pages = []
        for page in value["pages"]:
            page["regions"] = [
                region
                for region in page.get("regions") or []
                if str(region.get("evidence_id")) in allowed
            ]
            for region in page["regions"]:
                source_evidence_id = str(region["evidence_id"])
                region["source_evidence_id"] = source_evidence_id
                region["evidence_id"] = f"{scope_prefix}::{source_evidence_id}"
            # A sole product owns every line in the advertisement, including
            # parser lines that have no region assignment.  In a true
            # multi-product advertisement those lines are rejected by the
            # input validator because their owner cannot be inferred.
            page["unassigned_lines"] = (
                copy.deepcopy(page.get("unassigned_lines") or [])
                if single_product
                else []
            )
            if not page["regions"] and not page["unassigned_lines"]:
                continue
            region_count += len(page["regions"])
            line_count += (
                sum(len(region.get("lines") or []) for region in page["regions"])
                + len(page["unassigned_lines"])
            )
            empty_region_count += sum(
                1 for region in page["regions"] if not str(region.get("final_text") or "").strip()
            )
            pages.append(page)
        if not pages or region_count == 0:
            raise ValueError(f"product {product_id!r} has no scoped advertisement regions")
        value["pages"] = pages
        value["quality"] = {
            **copy.deepcopy(value.get("quality") or {}),
            "line_count": line_count,
            "line_partition_exact": True,
            "region_count": region_count,
            "empty_region_count": empty_region_count,
        }
        validate_integrated_input(value)
        scoped.append(value)
    return scoped


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
