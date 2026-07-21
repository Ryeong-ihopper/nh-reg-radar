from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nh_ad_parser_contracts import (
    DocumentInput,
    HwpHybridDocument,
    HwpHybridParserAdapter,
    HwpStructureAligner,
    NormalizedDocument,
)


def _document(
    parser_name: str,
    *,
    text: str,
    blocks: list[dict[str, object]] | None = None,
) -> NormalizedDocument:
    parser_rule_version = f"{parser_name}-normalized-v1"
    values = blocks or [
        {
            "textBlockId": f"{parser_name}-page-1",
            "fileId": "FILE-1",
            "pageNo": 1,
            "textPath": "pages/1",
            "textBlockType": "BODY",
            "rawText": text,
            "normalizedText": text,
            "rawStartOffset": 0,
            "rawEndOffset": len(text),
            "normalizedStartOffset": 0,
            "normalizedEndOffset": len(text),
            "parserName": parser_name,
            "parserVersion": "v1",
            "parserRuleVersion": parser_rule_version,
            "irVersion": "normalized-document-v1",
            "confidenceScore": 0.95,
            "confidenceStatus": "READABLE",
            "confidencePolicyVersion": "confidence-thresholds-v1",
        }
    ]
    return NormalizedDocument.model_validate(
        {
            "documentId": "doc-FILE-1",
            "sourceFileId": "FILE-1",
            "reviewId": "REV-1",
            "sourceFileType": "hwp",
            "parserName": parser_name,
            "parserVersion": "v1",
            "parserRuleVersion": parser_rule_version,
            "irVersion": "normalized-document-v1",
            "pages": [{"pageNo": 1, "width": 595, "height": 842, "unit": "point"}],
            "textBlocks": values,
            "layoutBlocks": [],
            "tables": [],
            "warnings": [],
            "confidence": {
                "score": 0.95,
                "status": "READABLE",
                "policyVersion": "confidence-thresholds-v1",
            },
            "rawArtifactRef": f"{parser_name}-raw-v1",
            "createdAt": datetime(2026, 7, 20, tzinfo=UTC),
        }
    )


def _structure_document() -> NormalizedDocument:
    blocks = []
    for index, (path, block_type, text) in enumerate(
        (
            ("s1.p1", "PARAGRAPH", "대출 대상\n공무원"),
            ("s1.p2", "PARAGRAPH", "대출 금리\n연 4.45%"),
        ),
        start=1,
    ):
        blocks.append(
            {
                "textBlockId": f"dp-{index}",
                "fileId": "FILE-1",
                "pageNo": 1,
                "textPath": path,
                "textBlockType": block_type,
                "rawText": text,
                "normalizedText": text,
                "rawStartOffset": 0,
                "rawEndOffset": len(text),
                "normalizedStartOffset": 0,
                "normalizedEndOffset": len(text),
                "parserName": "document-processor",
                "parserVersion": "v1",
                "parserRuleVersion": "document-processor-normalized-v1",
                "irVersion": "normalized-document-v1",
                "confidenceScore": 0.9,
                "confidenceStatus": "READABLE",
                "confidencePolicyVersion": "confidence-thresholds-v1",
            }
        )
    payload = _document("document-processor", text="", blocks=blocks).model_dump(
        mode="json", by_alias=True
    )
    payload.update(
        {
            "layoutBlocks": [
                {
                    "layoutBlockId": "layout-1",
                    "fileId": "FILE-1",
                    "pageNo": 1,
                    "layoutType": "PARAGRAPH",
                    "relatedTextBlockIds": ["dp-1"],
                    "confidenceScore": 0.9,
                }
            ],
            "tables": [
                {
                    "tableId": "table-1",
                    "pageNo": 1,
                    "textPath": "s1.p2.tbl1",
                    "cells": [["대출 금리", "연 4.45%"]],
                }
            ],
        }
    )
    return NormalizedDocument.model_validate(payload)


def _nonspace(value: str) -> str:
    return "".join(value.split())


def test_aligner_uses_rhwp_as_canonical_text_and_preserves_unmatched_ranges() -> None:
    canonical = "대출 대상\n공무원\n대출 금리\n연 4.45%\n추가 고지"

    merged = HwpStructureAligner().merge(_document("rhwp", text=canonical), _structure_document())

    assert merged.parser_name == "hwp-hybrid"
    assert {block.parser_name for block in merged.text_blocks} == {"hwp-hybrid"}
    assert _nonspace("".join(block.raw_text for block in merged.text_blocks)) == _nonspace(
        canonical
    )
    assert [block.text_block_type for block in merged.text_blocks] == [
        "PARAGRAPH",
        "PARAGRAPH",
        "UNALIGNED",
    ]
    assert merged.text_blocks[-1].raw_text.strip() == "추가 고지"
    assert merged.tables[0].text_path == "s1.p2.tbl1"
    assert merged.layout_blocks[0].related_text_block_ids == [merged.text_blocks[0].text_block_id]
    assert any(warning.code == "HWP_STRUCTURE_ALIGNMENT_INCOMPLETE" for warning in merged.warnings)
    assert merged.confidence.status.value == "LOW_CONFIDENCE"


def test_aligner_uses_related_structure_layout_coordinate_when_text_node_has_none() -> None:
    """A structural paragraph box is still a valid visual anchor for its text."""
    structure = _structure_document()
    payload = structure.model_dump(mode="json", by_alias=True)
    payload["layoutBlocks"][0]["coordinate"] = {
        "sourceWidth": 595,
        "sourceHeight": 842,
        "sourceUnit": "point",
        "x": 72,
        "y": 96,
        "width": 210,
        "height": 48,
        "normalizedX": 72 / 595,
        "normalizedY": 96 / 842,
        "normalizedWidth": 210 / 595,
        "normalizedHeight": 48 / 842,
        "coordinateConfidence": 0.90,
    }

    merged = HwpStructureAligner().merge(
        _document("rhwp", text="대출 대상\n공무원"),
        NormalizedDocument.model_validate(payload),
    )

    coordinate = merged.text_blocks[0].coordinate
    assert coordinate is not None
    assert (coordinate.normalized_x, coordinate.normalized_y) == (72 / 595, 96 / 842)


def test_aligner_keeps_rhwp_text_when_structure_source_is_unavailable() -> None:
    merged = HwpStructureAligner().merge(
        _document("rhwp", text="대출 대상\n공무원"),
        None,
        structure_error="DOCUMENT_PROCESSOR_SERVICE_UNAVAILABLE",
    )

    assert [block.raw_text for block in merged.text_blocks] == ["대출 대상\n공무원"]
    assert merged.text_blocks[0].text_block_type == "UNSTRUCTURED"
    assert merged.confidence.score == 0.79
    assert merged.confidence.status.value == "LOW_CONFIDENCE"
    assert merged.warnings[-1].code == "HWP_STRUCTURE_SOURCE_UNAVAILABLE"
    assert merged.warnings[-1].requires_review is True


def test_aligner_marks_unmatched_structure_nodes_for_review_without_losing_text() -> None:
    canonical = _document("rhwp", text="대출 대상\n공무원")
    structure = _structure_document()

    merged = HwpStructureAligner().merge(canonical, structure)

    assert _nonspace("".join(block.raw_text for block in merged.text_blocks)) == _nonspace(
        "대출 대상\n공무원"
    )
    assert merged.confidence.score == 0.79
    assert merged.warnings[-1].code == "HWP_STRUCTURE_ALIGNMENT_INCOMPLETE"
    assert merged.warnings[-1].requires_review is True


class _Adapter:
    def __init__(self, name: str, values: list[NormalizedDocument | RuntimeError]) -> None:
        self.name = name
        self.values = values
        self.calls = 0

    def parse(self, _document: DocumentInput) -> NormalizedDocument:
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        if isinstance(value, RuntimeError):
            raise value
        return value


def test_hybrid_adapter_retries_structure_source_and_returns_one_merged_document() -> None:
    text = _Adapter("rhwp", [_document("rhwp", text="대출 대상\n공무원")])
    structure = _Adapter(
        "document-processor",
        [RuntimeError("temporary"), RuntimeError("temporary"), _structure_document()],
    )
    adapter = HwpHybridParserAdapter(text, structure, structure_attempts=3)

    merged = adapter.parse(
        DocumentInput(
            source_file_id="FILE-1",
            review_id="REV-1",
            file_name="sample.hwp",
            mime_type="application/x-hwp",
            body=b"hwp",
        )
    )

    assert text.calls == 1
    assert structure.calls == 3
    assert merged.parser_name == "hwp-hybrid"
    assert isinstance(merged, HwpHybridDocument)
    assert [item.parser_name for item in merged.component_documents] == [
        "rhwp",
        "document-processor",
    ]
    assert "component_documents" not in merged.model_dump(mode="json", by_alias=True)


def test_hybrid_adapter_does_not_hide_canonical_text_source_failure() -> None:
    text = _Adapter("rhwp", [RuntimeError("rhwp failed")])
    structure = _Adapter("document-processor", [_structure_document()])

    with pytest.raises(RuntimeError, match="rhwp failed"):
        HwpHybridParserAdapter(text, structure).parse(
            DocumentInput(
                source_file_id="FILE-1",
                review_id="REV-1",
                file_name="sample.hwp",
                mime_type="application/x-hwp",
                body=b"hwp",
            )
        )

    assert structure.calls == 0
