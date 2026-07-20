"""document-processor private structure service for HWP/HWPX inputs."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from service import ParseRequest, _confidence_status, app_for, normalized_document

DOCUMENT_PROCESSOR_VERSION = os.getenv(
    "DOCUMENT_PROCESSOR_VERSION", "07c679086d80e674880dbad88c21757d8ae7dcf1"
)
ENGINE_NAME = "document-processor"
PARSER_RULE_VERSION = "document-processor-normalized-v1"
IR_VERSION = "normalized-document-v1"
CONFIDENCE_POLICY_VERSION = "confidence-thresholds-v1"


class DocumentProcessorEngine:
    name = ENGINE_NAME

    def parse(self, request: ParseRequest, body: bytes) -> dict[str, object]:
        extension = Path(request.file_name).suffix.casefold()
        if extension not in {".hwp", ".hwpx"}:
            raise ValueError("document-processor service accepts only HWP/HWPX")
        from document_processor import DocIR

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / request.file_name
            source.write_bytes(body)
            document = DocIR.from_file(
                source,
                doc_type=extension.removeprefix("."),
                include_tables=True,
            )
        return normalize_doc_ir(request, document, body)


def normalize_doc_ir(
    request: ParseRequest,
    document: Any,
    source_body: bytes,
) -> dict[str, object]:
    """Project a DocIR into structure-only NormalizedDocument v1 fields."""

    page_dimensions = {
        int(page.page_number): (page.width_pt, page.height_pt)
        for page in getattr(document, "pages", [])
    }
    blocks: list[dict[str, object]] = []
    layouts: list[dict[str, object]] = []
    tables: list[dict[str, object]] = []

    def add_text_block(
        node: Any,
        *,
        text: str,
        page_no: int,
        block_type: str,
        path: str,
        confidence: float,
    ) -> str | None:
        if not text.strip():
            return None
        block_id = _stable_id(request.review_id, "text", path)
        value: dict[str, object] = {
            "textBlockId": block_id,
            "fileId": request.source_file_id,
            "pageNo": page_no,
            "textPath": path,
            "textBlockType": block_type,
            "rawText": text,
            "normalizedText": text,
            "rawStartOffset": 0,
            "rawEndOffset": len(text),
            "normalizedStartOffset": 0,
            "normalizedEndOffset": len(text),
            "parserName": ENGINE_NAME,
            "parserVersion": DOCUMENT_PROCESSOR_VERSION,
            "parserRuleVersion": PARSER_RULE_VERSION,
            "irVersion": IR_VERSION,
            "confidenceScore": confidence,
            "confidenceStatus": _confidence_status(confidence),
            "confidencePolicyVersion": CONFIDENCE_POLICY_VERSION,
        }
        coordinate = _coordinate(getattr(node, "bbox", None), page_dimensions.get(page_no))
        if coordinate is not None:
            value["coordinate"] = coordinate
        blocks.append(value)
        return block_id

    def add_table(table: Any, *, page_no: int, fallback_path: str) -> None:
        table_path = _node_path(table, fallback_path)
        cell_ids: list[str] = []
        cell_values: list[list[str]] = []
        seen_cells: set[str] = set()
        for row_index, row in enumerate(getattr(table, "cells", []), start=1):
            row_values: list[str] = []
            for col_index, cell in enumerate(row, start=1):
                cell_text = _cell_text(cell)
                row_values.append(cell_text)
                cell_path = _node_path(cell, f"{table_path}.tr{row_index}.tc{col_index}")
                if cell_path in seen_cells:
                    continue
                seen_cells.add(cell_path)
                cell_id = add_text_block(
                    cell,
                    text=cell_text,
                    page_no=page_no,
                    block_type="TABLE_CELL",
                    path=cell_path,
                    confidence=0.90,
                )
                if cell_id is not None:
                    cell_ids.append(cell_id)
                for paragraph_index, paragraph in enumerate(
                    getattr(cell, "paragraphs", []), start=1
                ):
                    for table_index, nested in enumerate(getattr(paragraph, "tables", []), start=1):
                        add_table(
                            nested,
                            page_no=_page_no(paragraph, page_no),
                            fallback_path=(f"{cell_path}.p{paragraph_index}.tbl{table_index}"),
                        )
            cell_values.append(row_values)
        coordinate = _coordinate(getattr(table, "bbox", None), page_dimensions.get(page_no))
        table_id = _stable_id(request.review_id, "table", table_path)
        table_value: dict[str, object] = {
            "tableId": table_id,
            "pageNo": page_no,
            "textPath": table_path,
            "cells": cell_values,
        }
        if coordinate is not None:
            table_value["coordinate"] = coordinate
        tables.append(table_value)
        layouts.append(
            {
                "layoutBlockId": _stable_id(request.review_id, "layout", table_path),
                "fileId": request.source_file_id,
                "pageNo": page_no,
                "layoutType": "TABLE",
                "coordinate": coordinate,
                "relatedTextBlockIds": cell_ids,
                "confidenceScore": 0.90,
            }
        )

    for paragraph_index, paragraph in enumerate(getattr(document, "paragraphs", []), start=1):
        page_no = _page_no(paragraph, 1)
        path = _node_path(paragraph, f"s1.p{paragraph_index}")
        direct_text = _paragraph_text(paragraph)
        text_id = add_text_block(
            paragraph,
            text=direct_text,
            page_no=page_no,
            block_type="PARAGRAPH",
            path=path,
            confidence=0.92,
        )
        layouts.append(
            {
                "layoutBlockId": _stable_id(request.review_id, "layout", path),
                "fileId": request.source_file_id,
                "pageNo": page_no,
                "layoutType": "PARAGRAPH",
                "coordinate": _coordinate(
                    getattr(paragraph, "bbox", None), page_dimensions.get(page_no)
                ),
                "relatedTextBlockIds": [] if text_id is None else [text_id],
                "confidenceScore": 0.92,
            }
        )
        for table_index, table in enumerate(getattr(paragraph, "tables", []), start=1):
            add_table(table, page_no=page_no, fallback_path=f"{path}.tbl{table_index}")

    if not blocks:
        raise ValueError("document-processor emitted no structural text")
    seen_pages = {int(block["pageNo"]) for block in blocks if isinstance(block.get("pageNo"), int)}
    pages = []
    for page_no in sorted(seen_pages or {1}):
        width, height = page_dimensions.get(page_no, (None, None))
        page: dict[str, object] = {"pageNo": page_no}
        if width and height:
            page.update({"width": width, "height": height, "unit": "point"})
        pages.append(page)
    warnings = []
    if not page_dimensions:
        warnings.append(
            {
                "code": "DOCUMENT_STRUCTURE_PAGE_METADATA_UNAVAILABLE",
                "message": "원본 문서에서 페이지 크기 메타데이터를 확인하지 못했습니다.",
                "requiresReview": False,
            }
        )
    checksum = hashlib.sha256(source_body).hexdigest()
    return normalized_document(
        request,
        engine=ENGINE_NAME,
        version=DOCUMENT_PROCESSOR_VERSION,
        pages=pages,
        blocks=blocks,
        layout_blocks=layouts,
        tables=tables,
        warnings=warnings,
        raw_artifact_ref=f"document-processor:{DOCUMENT_PROCESSOR_VERSION}:{checksum}",
    )


def _paragraph_text(paragraph: Any) -> str:
    runs = getattr(paragraph, "runs", [])
    if runs:
        return "".join(str(getattr(run, "text", "")) for run in runs)
    if getattr(paragraph, "tables", []):
        return ""
    return str(getattr(paragraph, "text", ""))


def _cell_text(cell: Any) -> str:
    value = str(getattr(cell, "text", ""))
    if value:
        return value
    return "\n".join(
        str(getattr(paragraph, "text", ""))
        for paragraph in getattr(cell, "paragraphs", [])
        if str(getattr(paragraph, "text", ""))
    )


def _page_no(node: Any, fallback: int) -> int:
    value = getattr(node, "page_number", None)
    return int(value) if isinstance(value, int) and value >= 1 else fallback


def _node_path(node: Any, fallback: str) -> str:
    anchor = getattr(node, "native_anchor", None)
    if anchor is not None:
        value = getattr(anchor, "structural_path", None) or getattr(anchor, "debug_path", None)
        if value:
            return str(value)
    node_id = getattr(node, "node_id", None)
    return str(node_id or fallback)


def _coordinate(
    bbox: Any,
    dimensions: tuple[float | None, float | None] | None,
) -> dict[str, object] | None:
    if bbox is None or dimensions is None:
        return None
    source_width, source_height = dimensions
    if not source_width or not source_height:
        return None
    left = max(0.0, float(bbox.left_pt))
    right = min(float(source_width), float(bbox.right_pt))
    bottom = max(0.0, float(bbox.bottom_pt))
    top = min(float(source_height), float(bbox.top_pt))
    width = right - left
    height = top - bottom
    if width <= 0 or height <= 0:
        return None
    y = float(source_height) - top
    return {
        "sourceWidth": source_width,
        "sourceHeight": source_height,
        "sourceUnit": "point",
        "x": left,
        "y": y,
        "width": width,
        "height": height,
        "normalizedX": left / float(source_width),
        "normalizedY": y / float(source_height),
        "normalizedWidth": width / float(source_width),
        "normalizedHeight": height / float(source_height),
        "coordinateConfidence": 0.90,
    }


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]
    return f"dp-{digest}"


app = app_for(DocumentProcessorEngine())
