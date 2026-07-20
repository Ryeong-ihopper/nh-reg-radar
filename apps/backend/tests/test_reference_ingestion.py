from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.reference_ingestion import (
    ExtractedReference,
    ReferenceIngestionError,
    ReferenceIngestor,
    load_extractor,
    _metadata_input,
)
from nh_ad_backend.reference_document_parser import ParsedReferenceDocument
from nh_ad_backend.search import HybridSearch, InMemorySearchBackend, SearchDocument
from nh_ad_backend.standards import InMemoryStandardRepository, StandardService


PDF = b"%PDF-1.7\nsynthetic regulation\n%%EOF"
ACTOR = CurrentUser(
    "USR-SYNTH-STANDARD",
    "Synthetic Standard Manager",
    "DPT-SYNTH-COMPLIANCE",
    "Synthetic Compliance Team",
    ("STANDARD_MANAGER",),
    1,
)


class RecordingSearchBackend(InMemorySearchBackend):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.upserts: list[tuple[str, ...]] = []

    def upsert(self, documents: list[SearchDocument]) -> None:
        self.upserts.append(tuple(document.evidence_chunk_id for document in documents))
        super().upsert(documents)


@dataclass
class FixtureExtractor:
    calls: list[str]

    def extract(self, *, file_name: str, content: str) -> ExtractedReference:
        assert content
        self.calls.append(file_name)
        return ExtractedReference(
            title=f"{file_name} extracted",
            content="예금 광고에는 적용 금리 조건을 명확하게 표시해야 한다.",
            evidence_type="REGULATION",
            product_group="DEPOSIT",
            advertisement_type=None,
            rule_type="REQUIRED",
            importance="HIGH",
            effective_date=date(2026, 1, 1),
            expired_date=None,
            metadata={
                "agency": "Synthetic regulator",
                "documentName": file_name,
                "articleNo": "1",
                "effectiveDate": "2026-01-01",
                "revisionDate": "2026-01-01",
                "sourceUrl": f"https://example.invalid/{file_name}",
            },
        )


class FixtureParser:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def parse(
        self, *, file_name: str, source_file_id: str, source_hash: str, body: bytes
    ) -> ParsedReferenceDocument:
        assert source_file_id.startswith("REFSRC-")
        assert source_hash
        assert body
        self.calls.append(file_name)
        return ParsedReferenceDocument(
            content="예금 광고에는 적용 금리 조건을 명확하게 표시해야 한다.",
            parser_name="fixture-parser",
            parser_version="v1",
            parser_rule_version="fixture-structure-v1",
            ir_version="normalized-document-v1",
            text_block_count=1,
            layout_block_count=0,
            table_count=0,
            section_paths=("pages/1",),
        )


def services() -> tuple[
    StandardService, InMemoryStandardRepository, RecordingSearchBackend, RecordingSearchBackend
]:
    repository = InMemoryStandardRepository()
    keyword = RecordingSearchBackend("OPENSEARCH")
    vector = RecordingSearchBackend("QDRANT")
    counter = iter(range(1, 100))
    service = StandardService(
        repository,
        HybridSearch(keyword=keyword, vector=vector),
        now=lambda: datetime(2026, 7, 16, tzinfo=UTC),
        identifier=lambda prefix: f"{prefix}-{next(counter):04d}",
        environment="test",
    )
    return service, repository, keyword, vector


def test_ingests_local_pdfs_and_indexes_through_standard_service(tmp_path: Path) -> None:
    (tmp_path / "b.pdf").write_bytes(PDF)
    (tmp_path / "a.PDF").write_bytes(PDF + b"-a")
    standard_service, repository, keyword, vector = services()
    extractor = FixtureExtractor([])
    parser = FixtureParser()

    results = ReferenceIngestor(
        standard_service=standard_service,
        extractor=extractor,
        document_parser=parser,
        actor=ACTOR,
        source_dir=tmp_path,
    ).ingest()

    assert [result.source_file for result in results] == ["a.PDF", "b.pdf"]
    assert all(result.created for result in results)
    assert extractor.calls == ["a.PDF", "b.pdf"]
    assert parser.calls == ["a.PDF", "b.pdf"]
    assert len(repository.standards) == 2
    assert len(repository.chunks) == 2
    assert len(keyword.upserts) == len(vector.upserts) == 2
    assert all(result.reindex_job_id.startswith("SRJ-") for result in results)


def test_reingest_reuses_standard_and_retries_indexes_without_reextracting(tmp_path: Path) -> None:
    (tmp_path / "regulation.pdf").write_bytes(PDF)
    standard_service, repository, keyword, vector = services()
    extractor = FixtureExtractor([])
    parser = FixtureParser()
    ingestor = ReferenceIngestor(
        standard_service=standard_service,
        extractor=extractor,
        document_parser=parser,
        actor=ACTOR,
        source_dir=tmp_path,
    )

    first = ingestor.ingest()[0]
    second = ingestor.ingest()[0]

    assert first.standard_id == second.standard_id
    assert first.created is True and second.created is False
    assert extractor.calls == ["regulation.pdf"]
    assert parser.calls == ["regulation.pdf"]
    assert len(repository.standards) == 1
    assert len(keyword.upserts) == len(vector.upserts) == 2


def test_rejects_path_escape_non_pdf_and_invalid_pdf_header(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(PDF)
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a pdf")
    standard_service, _, _, _ = services()
    ingestor = ReferenceIngestor(
        standard_service=standard_service,
        extractor=FixtureExtractor([]),
        document_parser=FixtureParser(),
        actor=ACTOR,
        source_dir=tmp_path,
    )

    with pytest.raises(ReferenceIngestionError, match="source directory"):
        ingestor.ingest(["../outside.pdf"])
    with pytest.raises(ReferenceIngestionError, match="PDF signature"):
        ingestor.ingest(["invalid.pdf"])
    with pytest.raises(ReferenceIngestionError, match="PDF, HWP, and HWPX"):
        ingestor.ingest(["not-pdf.txt"])


def test_extractor_configuration_fails_closed() -> None:
    with pytest.raises(ReferenceIngestionError, match="NH_REFERENCE_EXTRACTOR"):
        load_extractor(None)


def test_metadata_input_is_bounded_without_changing_indexed_source_contract() -> None:
    content = "a" * 60_001
    value = _metadata_input(content)

    assert len(value) > 60_000
    assert value.startswith("a" * 48_000)
    assert value.endswith("a" * 12_000)
    assert "omitted only for metadata classification" in value
