"""Safe local reference-document ingestion boundary for regulations.

The module deliberately owns no provider client. A configured extractor converts
bounded PDF bytes into the existing StandardService input contract; persistence,
chunking, and Qdrant/OpenSearch writes remain owned by StandardService.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.main import build_services
from nh_ad_backend.reference_document_parser import (
    ParserServiceReferenceParser,
    ParsedReferenceDocument,
    ReferenceDocumentParser,
    ReferenceDocumentParserError,
)
from nh_ad_backend.settings import Settings, get_settings
from nh_ad_backend.standards import Standard, StandardService


MAX_REFERENCE_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_REFERENCE_METADATA_CHARS = 60_000
REFERENCE_SUFFIXES = frozenset({".pdf", ".hwp", ".hwpx"})
DEFAULT_SOURCE_DIR = Path("/reference-documents")
DEV_STANDARD_MANAGER = CurrentUser(
    "USR-SYNTH-STANDARD",
    "Synthetic Standard Manager",
    "DPT-SYNTH-COMPLIANCE",
    "Synthetic Compliance Team",
    ("STANDARD_MANAGER",),
    1,
)


class ReferenceIngestionError(RuntimeError):
    """Raised for a fail-closed local ingestion boundary violation."""


@dataclass(frozen=True)
class ExtractedReference:
    """Provider-neutral structured result expected from a PDF extractor."""

    title: str
    content: str
    evidence_type: str
    product_group: str | None
    advertisement_type: str | None
    rule_type: str
    importance: str
    effective_date: date | None
    expired_date: date | None
    metadata: dict[str, object]


@runtime_checkable
class ReferenceExtractor(Protocol):
    """Extract classification metadata from parser-normalized reference text."""

    def extract(self, *, file_name: str, content: str) -> ExtractedReference: ...


@dataclass(frozen=True)
class IngestionResult:
    source_file: str
    source_sha256: str
    standard_id: str
    evidence_id: str
    standard_version_id: str
    reindex_job_id: str
    created: bool


class ReferenceIngestor:
    """Read bounded PDFs, deduplicate them, then use the existing standards workflow."""

    def __init__(
        self,
        *,
        standard_service: StandardService,
        extractor: ReferenceExtractor,
        document_parser: ReferenceDocumentParser,
        actor: CurrentUser,
        source_dir: Path,
        embedding_model: str = "fixed-fixture-v1",
        max_document_bytes: int = MAX_REFERENCE_DOCUMENT_BYTES,
    ) -> None:
        if max_document_bytes <= 0:
            raise ReferenceIngestionError("max document size must be positive")
        try:
            root = source_dir.expanduser().resolve(strict=True)
        except OSError as exc:
            raise ReferenceIngestionError(f"source directory is unavailable: {source_dir}") from exc
        if not root.is_dir():
            raise ReferenceIngestionError(f"source directory is not a directory: {source_dir}")
        self._standard_service = standard_service
        self._extractor = extractor
        self._document_parser = document_parser
        self._actor = actor
        self._source_dir = root
        if not embedding_model.strip():
            raise ReferenceIngestionError("embedding model is required")
        self._embedding_model = embedding_model
        self._max_document_bytes = max_document_bytes

    def ingest(self, relative_files: Sequence[str] | None = None) -> list[IngestionResult]:
        paths = self._paths(relative_files)
        if not paths:
            raise ReferenceIngestionError(
                "source directory contains no supported reference documents"
            )
        return [self._ingest_one(path) for path in paths]

    def _paths(self, relative_files: Sequence[str] | None) -> list[Path]:
        if relative_files is None:
            names = sorted(
                path.relative_to(self._source_dir).as_posix()
                for path in self._source_dir.rglob("*")
                if path.suffix.casefold() in REFERENCE_SUFFIXES
            )
        else:
            names = list(relative_files)
        return [self._safe_reference_path(name) for name in names]

    def _safe_reference_path(self, relative_name: str) -> Path:
        supplied = Path(relative_name)
        if supplied.is_absolute() or supplied.suffix.casefold() not in REFERENCE_SUFFIXES:
            raise ReferenceIngestionError("only relative PDF, HWP, and HWPX files are accepted")
        unresolved = self._source_dir / supplied
        if unresolved.is_symlink():
            raise ReferenceIngestionError("symbolic-link reference inputs are not accepted")
        try:
            path = unresolved.resolve(strict=True)
            path.relative_to(self._source_dir)
        except (OSError, ValueError) as exc:
            raise ReferenceIngestionError(
                "reference document must remain inside the configured source directory"
            ) from exc
        if not path.is_file():
            raise ReferenceIngestionError("reference input is not a regular file")
        return path

    def _ingest_one(self, path: Path) -> IngestionResult:
        size = path.stat().st_size
        if size <= 0 or size > self._max_document_bytes:
            raise ReferenceIngestionError(
                f"reference document size must be between 1 and {self._max_document_bytes} bytes"
            )
        pdf_bytes = path.read_bytes()
        if len(pdf_bytes) > self._max_document_bytes:
            raise ReferenceIngestionError(
                f"reference document exceeds {self._max_document_bytes} bytes"
            )
        if path.suffix.casefold() == ".pdf" and not pdf_bytes.startswith(b"%PDF-"):
            raise ReferenceIngestionError("PDF signature is invalid")

        relative_name = path.relative_to(self._source_dir).as_posix()
        source_hash = hashlib.sha256(pdf_bytes).hexdigest()
        trace_id = f"reference-ingest-{source_hash[:24]}"
        existing = self._existing(source_hash, trace_id)
        parsed: ParsedReferenceDocument | None = None

        def parse() -> ParsedReferenceDocument:
            nonlocal parsed
            if parsed is None:
                try:
                    parsed = self._document_parser.parse(
                        file_name=relative_name,
                        source_file_id=f"REFSRC-{source_hash[:24].upper()}",
                        source_hash=source_hash,
                        body=pdf_bytes,
                    )
                except ReferenceDocumentParserError as exc:
                    raise ReferenceIngestionError(str(exc)) from exc
            return parsed

        if existing is None:
            parsed = parse()
            extracted = self._extractor.extract(
                file_name=relative_name, content=_metadata_input(parsed.content)
            )
            metadata = {
                **extracted.metadata,
                "sourceFileName": relative_name,
                "sourceSha256": source_hash,
                "parserName": parsed.parser_name,
                "parserVersion": parsed.parser_version,
                "parserRuleVersion": parsed.parser_rule_version,
                "parserIrVersion": parsed.ir_version,
                "textBlockCount": parsed.text_block_count,
                "layoutBlockCount": parsed.layout_block_count,
                "tableCount": parsed.table_count,
                "sectionPaths": list(parsed.section_paths),
            }
            created = self._standard_service.create(
                self._actor,
                title=extracted.title,
                evidence_type=extracted.evidence_type,
                product_group=extracted.product_group,
                advertisement_type=extracted.advertisement_type,
                rule_type=extracted.rule_type,
                importance=extracted.importance,
                effective_date=extracted.effective_date,
                expired_date=extracted.expired_date,
                metadata=metadata,
                content=parsed.content,
                trace_id=trace_id,
            )
            standard_id = created.standard_id
            evidence_id = created.evidence_id
            standard_version_id = created.standard_version_id
            parser_rule_version = parsed.parser_rule_version
            was_created = True
        else:
            standard, version = self._standard_service.manager_detail(
                self._actor, existing.standard_id, trace_id=trace_id
            )
            if not standard.metadata.get("parserRuleVersion"):
                parsed = parse()
                metadata = {
                    **version.metadata,
                    "parserName": parsed.parser_name,
                    "parserVersion": parsed.parser_version,
                    "parserRuleVersion": parsed.parser_rule_version,
                    "parserIrVersion": parsed.ir_version,
                    "textBlockCount": parsed.text_block_count,
                    "layoutBlockCount": parsed.layout_block_count,
                    "tableCount": parsed.table_count,
                    "sectionPaths": list(parsed.section_paths),
                }
                updated = self._standard_service.update(
                    self._actor,
                    standard.standard_id,
                    title=standard.title,
                    content=parsed.content,
                    effective_date=standard.effective_date,
                    expired_date=standard.expired_date,
                    metadata=metadata,
                    change_reason="initial parser provenance migration",
                    trace_id=trace_id,
                )
                standard_id = updated.standard_id
                evidence_id = updated.evidence_id
                standard_version_id = updated.standard_version_id
                parser_rule_version = parsed.parser_rule_version
            else:
                standard_id = standard.standard_id
                evidence_id = version.evidence_id
                standard_version_id = version.standard_version_id
                parser_rule_version = str(
                    standard.metadata.get("parserRuleVersion") or "direct-text-v1"
                )
            was_created = False

        job = self._standard_service.reindex(
            self._actor,
            standard_id,
            standard_version_id,
            reindex_scope="INDEX_ONLY",
            reason=f"local reference ingestion: {source_hash[:16]}",
            embedding_model=self._embedding_model,
            chunking_policy_version="reference-chunking-v1",
            search_schema_version="search-schema-v1",
            opensearch_analyzer_version="ko-v1",
            synonym_version="synonym-v1",
            target_indexes=("QDRANT", "OPENSEARCH"),
            trace_id=trace_id,
            parser_rule_version=parser_rule_version,
        )
        return IngestionResult(
            source_file=relative_name,
            source_sha256=source_hash,
            standard_id=standard_id,
            evidence_id=evidence_id,
            standard_version_id=standard_version_id,
            reindex_job_id=job.job_id,
            created=was_created,
        )

    def _existing(self, source_hash: str, trace_id: str) -> Standard | None:
        standards = self._standard_service.list_standards(
            self._actor, active_only=False, trace_id=trace_id
        )
        return next(
            (
                standard
                for standard in standards
                if standard.metadata.get("sourceSha256") == source_hash
            ),
            None,
        )


def load_extractor(spec: str | None) -> ReferenceExtractor:
    """Load a local extractor object/factory named as ``module:attribute``."""

    if not spec:
        raise ReferenceIngestionError(
            "NH_REFERENCE_EXTRACTOR must name an installed extractor as module:attribute"
        )
    module_name, separator, attribute_name = spec.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ReferenceIngestionError("extractor must use the module:attribute format")
    try:
        candidate = getattr(importlib.import_module(module_name), attribute_name)
        if isinstance(candidate, type):
            instance = candidate()
        elif isinstance(candidate, ReferenceExtractor):
            instance = candidate
        else:
            instance = candidate()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ReferenceIngestionError(f"extractor could not be loaded: {spec}") from exc
    if not isinstance(instance, ReferenceExtractor):
        raise ReferenceIngestionError("configured extractor does not implement extract()")
    return instance


def _metadata_input(content: str) -> str:
    """Bound metadata classification input without truncating the indexed source text."""
    if len(content) <= MAX_REFERENCE_METADATA_CHARS:
        return content
    head = MAX_REFERENCE_METADATA_CHARS * 4 // 5
    tail = MAX_REFERENCE_METADATA_CHARS - head
    return (
        content[:head]
        + "\n\n[... parser-normalized text omitted only for metadata classification ...]\n\n"
        + content[-tail:]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(os.getenv("NH_REFERENCE_SOURCE_DIR", str(DEFAULT_SOURCE_DIR))),
    )
    parser.add_argument(
        "--extractor",
        default=os.getenv("NH_REFERENCE_EXTRACTOR"),
        help="Installed extractor provider in module:attribute form.",
    )
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="Relative PDF path below source-dir; repeat to ingest selected files.",
    )
    return parser


def run_cli(
    options: argparse.Namespace,
    *,
    settings: Settings | None = None,
    extractor: ReferenceExtractor | None = None,
    standard_service: StandardService | None = None,
) -> list[IngestionResult]:
    resolved_settings = settings or get_settings()
    if resolved_settings.app_env != "dev":
        raise ReferenceIngestionError("local reference ingestion is allowed only in dev")
    resolved_extractor = extractor or load_extractor(cast(str | None, options.extractor))
    resolved_service = standard_service or build_services(resolved_settings).standards
    return ReferenceIngestor(
        standard_service=resolved_service,
        extractor=resolved_extractor,
        document_parser=ParserServiceReferenceParser(
            opendataloader_endpoint=resolved_settings.opendataloader_pdf_endpoint,
            rhwp_endpoint=resolved_settings.rhwp_endpoint,
            document_processor_endpoint=resolved_settings.document_processor_endpoint,
            timeout_seconds=resolved_settings.reference_parser_timeout_seconds,
            hwp_structure_attempts=resolved_settings.hwp_structure_attempts,
        ),
        actor=DEV_STANDARD_MANAGER,
        source_dir=cast(Path, options.source_dir),
        embedding_model=(
            resolved_settings.openai_embedding_model
            if resolved_settings.embedding_enabled
            else "fixed-fixture-v1"
        )
        or "fixed-fixture-v1",
    ).ingest(cast(list[str] | None, options.files))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        results = run_cli(_parser().parse_args(argv))
    except ReferenceIngestionError as exc:
        print(f"reference ingestion failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps([asdict(result) for result in results], ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the module command
    raise SystemExit(main())
