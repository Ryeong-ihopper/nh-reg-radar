"""Replaceable, structure-preserving parser boundary for reference documents."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import PurePath
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nh_ad_parser_contracts import (
    DocumentInput,
    HwpHybridParserAdapter,
    NormalizedDocument,
    ParserAdapter,
)


class ReferenceDocumentParserError(RuntimeError):
    """A reference document could not be parsed into the repository IR."""


@dataclass(frozen=True)
class ParsedReferenceDocument:
    """Normalized text plus parser provenance retained with a standard version."""

    content: str
    parser_name: str
    parser_version: str
    parser_rule_version: str
    ir_version: str
    text_block_count: int
    layout_block_count: int
    table_count: int
    section_paths: tuple[str, ...]


class ReferenceDocumentParser(Protocol):
    def parse(
        self, *, file_name: str, source_file_id: str, source_hash: str, body: bytes
    ) -> ParsedReferenceDocument: ...


class ParserServiceReferenceParser:
    """Use private engine services while exposing only ``NormalizedDocument`` to ingestion."""

    def __init__(
        self,
        *,
        opendataloader_endpoint: str,
        rhwp_endpoint: str,
        document_processor_endpoint: str,
        timeout_seconds: float,
        hwp_structure_attempts: int = 3,
    ) -> None:
        self._opendataloader = _ParserServiceAdapter(
            "opendataloader-pdf", opendataloader_endpoint, timeout_seconds=timeout_seconds
        )
        self._hwp_hybrid = HwpHybridParserAdapter(
            _ParserServiceAdapter("rhwp", rhwp_endpoint, timeout_seconds=timeout_seconds),
            _ParserServiceAdapter(
                "document-processor",
                document_processor_endpoint,
                timeout_seconds=timeout_seconds,
            ),
            structure_attempts=hwp_structure_attempts,
        )

    def parse(
        self, *, file_name: str, source_file_id: str, source_hash: str, body: bytes
    ) -> ParsedReferenceDocument:
        extension = PurePath(file_name).suffix.casefold()
        adapter: ParserAdapter
        if extension == ".pdf":
            adapter, mime_type = self._opendataloader, "application/pdf"
        elif extension in {".hwp", ".hwpx"}:
            adapter, mime_type = self._hwp_hybrid, _hwp_mime_type(extension)
        else:
            raise ReferenceDocumentParserError("REFERENCE_FILE_NOT_SUPPORTED")
        document_input = DocumentInput(
            source_file_id=source_file_id,
            review_id=f"reference-{source_hash[:24]}",
            file_name=file_name,
            mime_type=mime_type,
            body=body,
        )
        try:
            document = adapter.parse(document_input)
        except (RuntimeError, ValueError) as exc:
            raise ReferenceDocumentParserError(
                f"{adapter.name.upper()}_REFERENCE_PARSE_FAILED"
            ) from exc
        if document.source_file_id != source_file_id or document.parser_name != adapter.name:
            raise ReferenceDocumentParserError("REFERENCE_PARSER_IDENTITY_MISMATCH")
        blocks = sorted(
            document.text_blocks,
            key=lambda block: (
                block.page_no or 0,
                block.raw_start_offset if block.raw_start_offset is not None else 2**31,
                block.text_path or "",
                block.text_block_id,
            ),
        )
        content = "\n\n".join(
            block.normalized_text.strip() for block in blocks if block.normalized_text.strip()
        )
        if not content:
            raise ReferenceDocumentParserError("REFERENCE_DOCUMENT_HAS_NO_TEXT")
        return ParsedReferenceDocument(
            content=content,
            parser_name=document.parser_name,
            parser_version=document.parser_version,
            parser_rule_version=document.parser_rule_version,
            ir_version=document.ir_version,
            text_block_count=len(blocks),
            layout_block_count=len(document.layout_blocks),
            table_count=len(document.tables),
            section_paths=tuple(sorted({block.text_path for block in blocks if block.text_path})),
        )


class _ParserServiceAdapter:
    """Backend-local HTTP transport; composition stays in the shared contract package."""

    def __init__(self, name: str, endpoint: str, *, timeout_seconds: float) -> None:
        self.name = name
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        payload = {
            "sourceFileId": document.source_file_id,
            "reviewId": document.review_id,
            "fileName": document.file_name,
            "mimeType": document.mime_type,
            "contentBase64": base64.b64encode(document.body).decode("ascii"),
        }
        request = Request(
            f"{self._endpoint}/v1/parse",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                parsed = NormalizedDocument.model_validate_json(response.read())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ReferenceDocumentParserError(f"{self.name.upper()}_SERVICE_UNAVAILABLE") from exc
        if (
            parsed.source_file_id != document.source_file_id
            or parsed.review_id != document.review_id
            or parsed.parser_name != self.name
        ):
            raise ReferenceDocumentParserError(f"{self.name.upper()}_SERVICE_IDENTITY_MISMATCH")
        return parsed


def _hwp_mime_type(extension: str) -> str:
    return "application/vnd.hancom.hwp" if extension == ".hwpx" else "application/x-hwp"
