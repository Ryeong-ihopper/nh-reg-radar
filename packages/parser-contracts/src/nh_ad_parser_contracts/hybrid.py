"""Deterministic HWP/HWPX text-and-structure composition for ADR-0079."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import Field

from nh_ad_parser_contracts.models import (
    Confidence,
    Coordinate,
    LayoutBlock,
    NormalizedDocument,
    Table,
    TextBlock,
    Warning,
    confidence_status,
)
from nh_ad_parser_contracts.routing import DocumentInput, ParserAdapter

HYBRID_PARSER_NAME = "hwp-hybrid"
HYBRID_RULE_VERSION = "hwp-hybrid-alignment-v1"
CONFIDENCE_POLICY_VERSION = "confidence-thresholds-v1"


@dataclass(frozen=True)
class _AlignedRange:
    start: int
    end: int
    source: TextBlock | None


class HwpHybridDocument(NormalizedDocument):
    """Merged contract plus private component artifacts excluded from the wire IR."""

    component_documents: tuple[NormalizedDocument, ...] = Field(
        default_factory=tuple,
        exclude=True,
        repr=False,
    )


class HwpHybridParserAdapter:
    """Compose canonical rhwp text with replaceable document structure output."""

    name = HYBRID_PARSER_NAME

    def __init__(
        self,
        text_source: ParserAdapter,
        structure_source: ParserAdapter,
        *,
        structure_attempts: int = 3,
        aligner: HwpStructureAligner | None = None,
    ) -> None:
        if structure_attempts < 1:
            raise ValueError("structure_attempts must be at least one")
        self._text_source = text_source
        self._structure_source = structure_source
        self._structure_attempts = structure_attempts
        self._aligner = aligner or HwpStructureAligner()

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        canonical = self._text_source.parse(document)
        structure: NormalizedDocument | None = None
        structure_error: str | None = None
        for _attempt in range(self._structure_attempts):
            try:
                structure = self._structure_source.parse(document)
                structure_error = None
                break
            except RuntimeError as exc:
                structure_error = str(exc) or type(exc).__name__
        merged = self._aligner.merge(
            canonical,
            structure,
            structure_error=structure_error,
        )
        components = (canonical,) if structure is None else (canonical, structure)
        return HwpHybridDocument.model_validate(
            {
                **merged.model_dump(mode="python"),
                "component_documents": components,
            }
        )


class HwpStructureAligner:
    """Align structure nodes to canonical text without replacing or dropping text."""

    def merge(
        self,
        canonical: NormalizedDocument,
        structure: NormalizedDocument | None,
        *,
        structure_error: str | None = None,
    ) -> NormalizedDocument:
        self._validate_canonical(canonical)
        if structure is None:
            return self._unstructured(canonical, structure_error)
        self._validate_identity(canonical, structure)

        canonical_pages = self._page_texts(canonical)
        aligned = self._aligned_ranges(canonical_pages, structure)
        if not aligned:
            return self._unstructured(canonical, "DOCUMENT_PROCESSOR_STRUCTURE_EMPTY")

        output_blocks: list[TextBlock] = []
        source_to_output: dict[str, str] = {}
        expected_structure_ids = {
            block.text_block_id
            for block in structure.text_blocks
            if block.normalized_text.strip() and (block.page_no or 1) in canonical_pages
        }
        matched_structure_ids = {
            item.source.text_block_id
            for ranges in aligned.values()
            for item in ranges
            if item.source is not None
        }
        incomplete = not expected_structure_ids.issubset(matched_structure_ids)
        parser_version = self._parser_version(canonical, structure)
        structure_coordinates = self._structure_coordinates(structure)
        for page_no in sorted(canonical_pages):
            page_text = canonical_pages[page_no]
            page_ranges = aligned.get(page_no, [])
            ranges = [
                *page_ranges,
                *self._uncovered_ranges(page_text, page_ranges),
            ]
            for item in sorted(ranges, key=lambda value: (value.start, value.end)):
                raw_text = page_text[item.start : item.end]
                if not raw_text or (item.source is None and not raw_text.strip()):
                    continue
                block = self._hybrid_block(
                    canonical,
                    item.source,
                    page_no=page_no,
                    start=item.start,
                    end=item.end,
                    raw_text=raw_text,
                    unmatched=item.source is None,
                    parser_version=parser_version,
                    coordinate=(
                        structure_coordinates.get(item.source.text_block_id)
                        if item.source is not None
                        else None
                    ),
                )
                output_blocks.append(block)
                if item.source is None:
                    incomplete = True
                else:
                    source_to_output[item.source.text_block_id] = block.text_block_id

        if not output_blocks:
            return self._unstructured(canonical, "DOCUMENT_PROCESSOR_ALIGNMENT_EMPTY")

        warnings = [*canonical.warnings, *structure.warnings]
        if incomplete:
            warnings.append(
                Warning(
                    code="HWP_STRUCTURE_ALIGNMENT_INCOMPLETE",
                    message=(
                        "일부 기준 텍스트 또는 구조 노드를 완전히 정렬하지 못했습니다. "
                        "rhwp 텍스트는 누락 없이 보존했습니다."
                    ),
                    requiresReview=True,
                )
            )
        layout_blocks = self._layout_blocks(canonical, structure, source_to_output)
        tables = self._tables(structure)
        score = min(block.confidence_score for block in output_blocks)
        if incomplete:
            score = min(score, 0.79)
        return NormalizedDocument(
            documentId=canonical.document_id,
            sourceFileId=canonical.source_file_id,
            reviewId=canonical.review_id,
            sourceFileType=canonical.source_file_type,
            parserName=HYBRID_PARSER_NAME,
            parserVersion=parser_version,
            parserRuleVersion=HYBRID_RULE_VERSION,
            irVersion=canonical.ir_version,
            pages=structure.pages or canonical.pages,
            textBlocks=output_blocks,
            layoutBlocks=layout_blocks,
            tables=tables,
            warnings=warnings,
            confidence=Confidence(
                score=score,
                status=confidence_status(score),
                policyVersion=CONFIDENCE_POLICY_VERSION,
            ),
            rawArtifactRef=self._artifact_reference(canonical, structure),
            createdAt=max(canonical.created_at, structure.created_at),
        )

    @staticmethod
    def _structure_coordinates(structure: NormalizedDocument) -> dict[str, Coordinate]:
        """Prefer exact text bounds, then the owning layout block's verified bounds.

        document-processor can expose a paragraph/table layout box even when the
        nested text node has no own bbox.  The layout box remains a truthful
        visual anchor and lets the review UI annotate the rendered source rather
        than presenting a detached Text IR highlight.
        """
        values = {
            block.text_block_id: block.coordinate
            for block in structure.text_blocks
            if block.coordinate is not None
        }
        for layout in structure.layout_blocks:
            if layout.coordinate is None:
                continue
            for text_block_id in layout.related_text_block_ids:
                values.setdefault(text_block_id, layout.coordinate)
        return values

    @staticmethod
    def _validate_canonical(canonical: NormalizedDocument) -> None:
        if canonical.parser_name != "rhwp":
            raise ValueError("HWP_HYBRID_REQUIRES_RHWP_TEXT_SOURCE")
        if not any(block.raw_text.strip() for block in canonical.text_blocks):
            raise ValueError("HWP_HYBRID_CANONICAL_TEXT_EMPTY")

    @staticmethod
    def _validate_identity(canonical: NormalizedDocument, structure: NormalizedDocument) -> None:
        if structure.parser_name != "document-processor":
            raise ValueError("HWP_HYBRID_REQUIRES_DOCUMENT_PROCESSOR_STRUCTURE")
        if (
            canonical.source_file_id != structure.source_file_id
            or canonical.review_id != structure.review_id
        ):
            raise ValueError("HWP_HYBRID_SOURCE_IDENTITY_MISMATCH")

    @staticmethod
    def _page_texts(document: NormalizedDocument) -> dict[int, str]:
        by_page: dict[int, list[TextBlock]] = {}
        for block in document.text_blocks:
            by_page.setdefault(block.page_no or 1, []).append(block)
        return {
            page_no: "\n".join(
                block.raw_text
                for block in sorted(
                    blocks,
                    key=lambda value: (
                        value.raw_start_offset or 0,
                        value.text_path or "",
                        value.text_block_id,
                    ),
                )
                if block.raw_text
            )
            for page_no, blocks in by_page.items()
        }

    def _aligned_ranges(
        self,
        canonical_pages: dict[int, str],
        structure: NormalizedDocument,
    ) -> dict[int, list[_AlignedRange]]:
        values: dict[int, list[_AlignedRange]] = {}
        cursors: dict[int, int] = {}
        for block in structure.text_blocks:
            page_no = block.page_no or 1
            canonical = canonical_pages.get(page_no)
            if canonical is None or not block.normalized_text.strip():
                continue
            match = self._match(canonical, block.normalized_text, cursors.get(page_no, 0))
            if match is None:
                continue
            start, end = match
            values.setdefault(page_no, []).append(_AlignedRange(start, end, block))
            cursors[page_no] = end
        return values

    @staticmethod
    def _match(canonical: str, candidate: str, cursor: int) -> tuple[int, int] | None:
        exact = canonical.find(candidate, cursor)
        if exact >= 0:
            return exact, exact + len(candidate)

        canonical_chars = [
            (character, index)
            for index, character in enumerate(canonical)
            if not character.isspace() and index >= cursor
        ]
        candidate_compact = "".join(character for character in candidate if not character.isspace())
        if not canonical_chars or not candidate_compact:
            return None
        compact = "".join(character for character, _index in canonical_chars)
        compact_start = compact.find(candidate_compact)
        if compact_start < 0:
            return None
        raw_start = canonical_chars[compact_start][1]
        raw_end = canonical_chars[compact_start + len(candidate_compact) - 1][1] + 1
        return raw_start, raw_end

    @staticmethod
    def _uncovered_ranges(text: str, aligned: list[_AlignedRange]) -> list[_AlignedRange]:
        values: list[_AlignedRange] = []
        cursor = 0
        for item in sorted(aligned, key=lambda value: (value.start, value.end)):
            if item.start > cursor:
                values.append(_AlignedRange(cursor, item.start, None))
            cursor = max(cursor, item.end)
        if cursor < len(text):
            values.append(_AlignedRange(cursor, len(text), None))
        return values

    def _hybrid_block(
        self,
        canonical: NormalizedDocument,
        source: TextBlock | None,
        *,
        page_no: int,
        start: int,
        end: int,
        raw_text: str,
        unmatched: bool,
        parser_version: str,
        coordinate: Coordinate | None,
    ) -> TextBlock:
        if source is None:
            if not unmatched:
                raise ValueError("HWP_HYBRID_UNMATCHED_SOURCE_INCONSISTENT")
            score = min(canonical.confidence.score, 0.79)
            text_path = f"pages/{page_no}/unaligned/{start}-{end}"
            text_block_type = "UNALIGNED"
            coordinate = None
        else:
            score = min(canonical.confidence.score, source.confidence_score)
            text_path = source.text_path or f"pages/{page_no}/structure/{start}-{end}"
            text_block_type = source.text_block_type
        return TextBlock(
            textBlockId=self._stable_id(
                "text", canonical.review_id, page_no, text_path, start, end
            ),
            fileId=canonical.source_file_id,
            pageNo=page_no,
            textPath=text_path,
            textBlockType=text_block_type,
            rawText=raw_text,
            normalizedText=raw_text,
            rawStartOffset=start,
            rawEndOffset=end,
            normalizedStartOffset=start,
            normalizedEndOffset=end,
            parserName=HYBRID_PARSER_NAME,
            parserVersion=parser_version,
            parserRuleVersion=HYBRID_RULE_VERSION,
            irVersion=canonical.ir_version,
            confidenceScore=score,
            confidenceStatus=confidence_status(score),
            confidencePolicyVersion=CONFIDENCE_POLICY_VERSION,
            coordinate=coordinate,
        )

    def _unstructured(
        self, canonical: NormalizedDocument, structure_error: str | None
    ) -> NormalizedDocument:
        score = min(canonical.confidence.score, 0.79)
        version = self._parser_version(canonical, None)
        blocks = [
            TextBlock(
                textBlockId=self._stable_id(
                    "text",
                    canonical.review_id,
                    block.page_no or 1,
                    block.text_path or block.text_block_id,
                    block.raw_start_offset or 0,
                    block.raw_end_offset or len(block.raw_text),
                ),
                fileId=canonical.source_file_id,
                pageNo=block.page_no,
                textPath=block.text_path or f"pages/{block.page_no or 1}",
                textBlockType="UNSTRUCTURED",
                rawText=block.raw_text,
                normalizedText=block.raw_text,
                rawStartOffset=block.raw_start_offset,
                rawEndOffset=block.raw_end_offset,
                normalizedStartOffset=block.raw_start_offset,
                normalizedEndOffset=block.raw_end_offset,
                parserName=HYBRID_PARSER_NAME,
                parserVersion=version,
                parserRuleVersion=HYBRID_RULE_VERSION,
                irVersion=canonical.ir_version,
                confidenceScore=score,
                confidenceStatus=confidence_status(score),
                confidencePolicyVersion=CONFIDENCE_POLICY_VERSION,
                coordinate=block.coordinate,
            )
            for block in canonical.text_blocks
        ]
        warning = Warning(
            code="HWP_STRUCTURE_SOURCE_UNAVAILABLE",
            message=(
                "document-processor 구조 보강에 실패해 rhwp 기준 텍스트를 "
                f"비구조화 상태로 보존했습니다: {structure_error or 'unknown'}"
            ),
            requiresReview=True,
        )
        return NormalizedDocument(
            documentId=canonical.document_id,
            sourceFileId=canonical.source_file_id,
            reviewId=canonical.review_id,
            sourceFileType=canonical.source_file_type,
            parserName=HYBRID_PARSER_NAME,
            parserVersion=version,
            parserRuleVersion=HYBRID_RULE_VERSION,
            irVersion=canonical.ir_version,
            pages=canonical.pages,
            textBlocks=blocks,
            layoutBlocks=[],
            tables=[],
            warnings=[*canonical.warnings, warning],
            confidence=Confidence(
                score=score,
                status=confidence_status(score),
                policyVersion=CONFIDENCE_POLICY_VERSION,
            ),
            rawArtifactRef=self._artifact_reference(canonical, None),
            createdAt=canonical.created_at,
        )

    def _layout_blocks(
        self,
        canonical: NormalizedDocument,
        structure: NormalizedDocument,
        source_to_output: dict[str, str],
    ) -> list[LayoutBlock]:
        values = []
        for block in structure.layout_blocks:
            related = [
                source_to_output[source_id]
                for source_id in block.related_text_block_ids
                if source_id in source_to_output
            ]
            values.append(
                LayoutBlock(
                    layoutBlockId=self._stable_id(
                        "layout", canonical.review_id, block.layout_block_id
                    ),
                    fileId=canonical.source_file_id,
                    pageNo=block.page_no,
                    layoutType=block.layout_type,
                    coordinate=block.coordinate,
                    relatedTextBlockIds=related,
                    confidenceScore=block.confidence_score,
                )
            )
        return values

    def _tables(self, structure: NormalizedDocument) -> list[Table]:
        return [
            table.model_copy(
                update={"table_id": self._stable_id("table", structure.review_id, table.table_id)}
            )
            for table in structure.tables
        ]

    @staticmethod
    def _parser_version(
        canonical: NormalizedDocument,
        structure: NormalizedDocument | TextBlock | None,
    ) -> str:
        structure_version = "unavailable" if structure is None else structure.parser_version
        return f"rhwp-{canonical.parser_version}+dp-{structure_version}+align-v1"

    @staticmethod
    def _artifact_reference(
        canonical: NormalizedDocument, structure: NormalizedDocument | None
    ) -> str:
        canonical_hash = hashlib.sha256(
            canonical.model_dump_json(by_alias=True).encode("utf-8")
        ).hexdigest()[:16]
        structure_hash = (
            "unavailable"
            if structure is None
            else hashlib.sha256(
                structure.model_dump_json(by_alias=True).encode("utf-8")
            ).hexdigest()[:16]
        )
        return f"hwp-hybrid:rhwp={canonical_hash};document-processor={structure_hash}"

    @staticmethod
    def _stable_id(prefix: str, *parts: object) -> str:
        digest = hashlib.sha256(":".join(str(part) for part in parts).encode()).hexdigest()[:24]
        return f"{prefix}-{digest}"
