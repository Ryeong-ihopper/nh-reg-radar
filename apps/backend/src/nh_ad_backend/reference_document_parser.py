"""Replaceable, structure-preserving parser boundary for reference documents."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import PurePath
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nh_ad_parser_contracts import NormalizedDocument


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
        timeout_seconds: float,
    ) -> None:
        self._opendataloader_endpoint = opendataloader_endpoint.rstrip("/")
        self._rhwp_endpoint = rhwp_endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def parse(
        self, *, file_name: str, source_file_id: str, source_hash: str, body: bytes
    ) -> ParsedReferenceDocument:
        extension = PurePath(file_name).suffix.casefold()
        if extension == ".pdf":
            engine, endpoint, mime_type = (
                "opendataloader-pdf",
                self._opendataloader_endpoint,
                "application/pdf",
            )
        elif extension in {".hwp", ".hwpx"}:
            engine, endpoint, mime_type = "rhwp", self._rhwp_endpoint, _hwp_mime_type(extension)
        else:
            raise ReferenceDocumentParserError("REFERENCE_FILE_NOT_SUPPORTED")
        payload = {
            "sourceFileId": source_file_id,
            "reviewId": f"reference-{source_hash[:24]}",
            "fileName": file_name,
            "mimeType": mime_type,
            "contentBase64": base64.b64encode(body).decode("ascii"),
        }
        request = Request(
            f"{endpoint}/v1/parse",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                document = NormalizedDocument.model_validate_json(response.read())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ReferenceDocumentParserError(f"{engine.upper()}_REFERENCE_PARSE_FAILED") from exc
        if document.source_file_id != source_file_id or document.parser_name != engine:
            raise ReferenceDocumentParserError("REFERENCE_PARSER_IDENTITY_MISMATCH")
        blocks = sorted(
            document.text_blocks,
            key=lambda block: (block.page_no or 0, block.text_path or "", block.text_block_id),
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


def _hwp_mime_type(extension: str) -> str:
    return "application/vnd.hancom.hwp" if extension == ".hwpx" else "application/x-hwp"
