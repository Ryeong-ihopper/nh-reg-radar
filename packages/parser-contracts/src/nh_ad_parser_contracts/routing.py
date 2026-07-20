"""File-type routing behind replaceable parser/OCR adapters."""

from dataclasses import dataclass, replace
from pathlib import PurePath
from typing import Protocol

from nh_ad_parser_contracts.models import NormalizedDocument


@dataclass(frozen=True)
class DocumentInput:
    source_file_id: str
    review_id: str
    file_name: str
    mime_type: str
    body: bytes
    scanned_pdf: bool = False
    complex_layout: bool = False
    external_ai_allowed: bool = False


@dataclass(frozen=True)
class ParserRoute:
    primary_adapter: str
    secondary_adapters: tuple[str, ...]
    quality_rerun_reason: str | None = None


@dataclass(frozen=True)
class ParserAttempt:
    adapter_name: str
    normalized_document: NormalizedDocument
    attempt_no: int
    is_primary_attempt: bool
    is_selected_output: bool = False
    rerun_reason_code: str | None = None


@dataclass(frozen=True)
class ParserSelection:
    attempts: tuple[ParserAttempt, ...]

    @property
    def selected_document(self) -> NormalizedDocument:
        selected = [attempt for attempt in self.attempts if attempt.is_selected_output]
        if len(selected) != 1:
            raise ValueError("PARSER_SELECTION_REQUIRES_EXACTLY_ONE_OUTPUT")
        return selected[0].normalized_document


class ParserAdapter(Protocol):
    name: str

    def parse(self, document: DocumentInput) -> NormalizedDocument: ...


class AdapterNotConfigured(LookupError):
    pass


class ParserRouter:
    """ADR-0079 routing without importing any provider SDK."""

    def __init__(self, adapters: dict[str, ParserAdapter] | None = None) -> None:
        self._adapters = adapters or {}

    def route(self, document: DocumentInput) -> ParserRoute:
        extension = PurePath(document.file_name).suffix.casefold()
        if extension in {".hwp", ".hwpx"}:
            return ParserRoute("hwp-hybrid", ())
        if extension == ".pdf":
            if document.scanned_pdf:
                return ParserRoute("paddleocr", ("opendataloader-pdf", "mineru"))
            reason = "TABLE_EXTRACTION_MISSING" if document.complex_layout else None
            return ParserRoute("opendataloader-pdf", ("mineru",), reason)
        if extension in {".jpg", ".jpeg", ".png"}:
            secondary = ("vlm-ocr",) if document.external_ai_allowed else ()
            return ParserRoute("paddleocr", secondary)
        raise ValueError("FILE_NOT_SUPPORTED")

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        return self.parse_with_attempts(document).selected_document

    def parse_with_attempts(self, document: DocumentInput) -> ParserSelection:
        route = self.route(document)
        try:
            adapter = self._adapters[route.primary_adapter]
        except KeyError as exc:
            raise AdapterNotConfigured(route.primary_adapter) from exc
        attempts = [
            ParserAttempt(
                adapter_name=route.primary_adapter,
                normalized_document=adapter.parse(document),
                attempt_no=1,
                is_primary_attempt=True,
                rerun_reason_code=route.quality_rerun_reason,
            )
        ]
        if route.quality_rerun_reason is not None:
            for adapter_name in route.secondary_adapters:
                secondary = self._adapters.get(adapter_name)
                if secondary is None:
                    continue
                attempts.append(
                    ParserAttempt(
                        adapter_name=adapter_name,
                        normalized_document=secondary.parse(document),
                        attempt_no=len(attempts) + 1,
                        is_primary_attempt=False,
                        rerun_reason_code=route.quality_rerun_reason,
                    )
                )
        selected = max(attempts, key=self._candidate_rank)
        return ParserSelection(
            tuple(replace(attempt, is_selected_output=attempt is selected) for attempt in attempts)
        )

    @staticmethod
    def _candidate_rank(attempt: ParserAttempt) -> tuple[float, int, float, int, int, int]:
        """Apply ADR-0073 criteria with a stable primary-first tie break."""
        document = attempt.normalized_document
        required_fields = sum(
            bool(value)
            for value in (
                document.document_id,
                document.source_file_id,
                document.review_id,
                document.source_file_type,
                document.parser_name,
                document.parser_version,
                document.parser_rule_version,
                document.ir_version,
                document.pages,
                document.text_blocks,
            )
        )
        locations = [
            block.coordinate is not None
            or (
                block.text_path is not None
                and block.raw_start_offset is not None
                and block.raw_end_offset is not None
                and block.normalized_start_offset is not None
                and block.normalized_end_offset is not None
            )
            for block in document.text_blocks
        ]
        locations.extend(block.coordinate is not None for block in document.layout_blocks)
        locations.extend(
            table.coordinate is not None or table.text_path is not None for table in document.tables
        )
        location_completeness = sum(locations) / len(locations) if locations else 0.0
        readable_phrases = sum(
            bool(block.normalized_text.strip()) and block.confidence_status.value == "READABLE"
            for block in document.text_blocks
        )
        return (
            document.confidence.score,
            required_fields,
            location_completeness,
            -len(document.warnings),
            readable_phrases,
            -attempt.attempt_no,
        )
