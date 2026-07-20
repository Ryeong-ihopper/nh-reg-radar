"""Deterministic M3 chunking and hybrid-search boundary.

The module deliberately has no embedding implementation.  M3 callers inject fixed
vector scores (tests/fixtures) or a real index adapter at the boundary; an unavailable
backend is an explicit error and is never treated as an empty, successful search.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol, Sequence


SearchMode = Literal["KEYWORD", "VECTOR", "HYBRID"]
_RRF_RANK_CONSTANT = 60


@dataclass(frozen=True)
class DirectTextChunk:
    evidence_chunk_id: str
    chunk_no: int
    chunk_text: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class SearchDocument:
    evidence_chunk_id: str
    evidence_id: str
    standard_id: str
    standard_version_id: str
    evidence_type: str
    title: str
    chunk_text: str
    article_no: str | None
    section_path: str | None
    product_group: str | None
    advertisement_type: str | None
    rule_type: str
    importance: str
    effective_date: date | None
    expired_date: date | None
    version: str
    is_active: bool = True
    opensearch_analyzer_version: str | None = None
    synonym_version: str | None = None


@dataclass(frozen=True)
class BackendHit:
    document: SearchDocument
    score: float
    highlights: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchHit:
    document: SearchDocument
    rank_no: int
    relevance_score: float
    match_source: SearchMode
    highlights: dict[str, list[str]] = field(default_factory=dict)


class SearchInfrastructureError(RuntimeError):
    """Raised when a requested search backend cannot return a trustworthy result."""

    def __init__(self, backend: str, message: str = "search backend unavailable") -> None:
        self.backend = backend
        super().__init__(f"{backend}: {message}")


class SearchBackend(Protocol):
    name: str

    def search(
        self,
        keyword: str,
        *,
        limit: int,
        effective_date: date,
        filters: dict[str, str],
    ) -> list[BackendHit]: ...

    def upsert(self, documents: Sequence[SearchDocument]) -> None: ...

    def exclude(self, standard_id: str) -> None: ...


def deterministic_index_id(
    environment: str,
    standard_version_id: str,
    evidence_chunk_id: str,
    embedding_model: str,
    chunking_policy_version: str,
) -> str:
    """Return the ADR-0070 logical point/document id without hidden randomness."""

    values = (
        environment,
        standard_version_id,
        evidence_chunk_id,
        embedding_model,
        chunking_policy_version,
    )
    if any(not value or ":" in value for value in values):
        raise ValueError("deterministic index id components must be non-empty and colon-free")
    return ":".join(values)


def direct_text_chunks(
    standard_version_id: str,
    content: str,
    *,
    max_characters: int = 800,
) -> list[DirectTextChunk]:
    """Chunk directly entered text only, preserving deterministic source offsets.

    Paragraphs are retained when possible.  Oversized paragraphs are split at a word
    boundary (or at the hard character boundary for unbroken input).  No file parser or
    OCR behavior belongs in this M3 function.
    """

    if not standard_version_id:
        raise ValueError("standard_version_id is required")
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        raise ValueError("content is required")

    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", normalized, re.DOTALL):
        paragraph = re.sub(r"[ \t\n]+", " ", match.group(0)).strip()
        if not paragraph:
            continue
        cursor = 0
        while cursor < len(paragraph):
            end = min(cursor + max_characters, len(paragraph))
            if end < len(paragraph):
                boundary = paragraph.rfind(" ", cursor, end + 1)
                if boundary > cursor:
                    end = boundary
            text = paragraph[cursor:end].strip()
            if text:
                relative = match.group(0).find(text.split(" ", 1)[0])
                source_start = match.start() + max(relative, 0)
                spans.append((source_start, source_start + len(text), text))
            cursor = end
            while cursor < len(paragraph) and paragraph[cursor].isspace():
                cursor += 1

    chunks: list[DirectTextChunk] = []
    for chunk_no, (start, end, text) in enumerate(spans, 1):
        digest = (
            hashlib.sha256(f"{standard_version_id}\0{chunk_no}\0{text}".encode("utf-8"))
            .hexdigest()[:20]
            .upper()
        )
        chunks.append(
            DirectTextChunk(
                evidence_chunk_id=f"ECH-{digest}",
                chunk_no=chunk_no,
                chunk_text=text,
                source_start=start,
                source_end=end,
            )
        )
    return chunks


class InMemorySearchBackend:
    """Deterministic fixed-score backend for unit/contract fixtures."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._documents: dict[str, SearchDocument] = {}
        self._scores: dict[str, float] = {}
        self.fail_next = False

    def replace(
        self, documents: Sequence[SearchDocument], scores: dict[str, float] | None = None
    ) -> None:
        self._documents = {document.evidence_chunk_id: document for document in documents}
        self._scores = dict(scores or {})

    def search(
        self,
        keyword: str,
        *,
        limit: int,
        effective_date: date,
        filters: dict[str, str],
    ) -> list[BackendHit]:
        if self.fail_next:
            self.fail_next = False
            raise SearchInfrastructureError(self.name)
        terms = tuple(term.casefold() for term in keyword.split() if term)
        results: list[BackendHit] = []
        for document in self._documents.values():
            if not _eligible(document, effective_date, filters):
                continue
            searchable = f"{document.title} {document.chunk_text}".casefold()
            lexical = sum(searchable.count(term) for term in terms)
            if document.evidence_chunk_id not in self._scores and lexical == 0:
                continue
            score = self._scores.get(document.evidence_chunk_id, float(lexical))
            results.append(BackendHit(document, score))
        return sorted(
            results,
            key=lambda hit: (-hit.score, hit.document.evidence_chunk_id),
        )[:limit]

    def upsert(self, documents: Sequence[SearchDocument]) -> None:
        for document in documents:
            self._documents[document.evidence_chunk_id] = document

    def exclude(self, standard_id: str) -> None:
        self._documents = {
            identifier: document
            for identifier, document in self._documents.items()
            if document.standard_id != standard_id
        }
        self._scores = {
            identifier: score
            for identifier, score in self._scores.items()
            if identifier in self._documents
        }


def _eligible(document: SearchDocument, effective_on: date, filters: dict[str, str]) -> bool:
    if not document.is_active:
        return False
    if document.effective_date and document.effective_date > effective_on:
        return False
    if document.expired_date and document.expired_date < effective_on:
        return False
    return all(
        getattr(document, field, None) == expected
        for field, expected in filters.items()
        if expected is not None
    )


class HybridSearch:
    """Fail-closed deterministic keyword/vector/hybrid result merger."""

    def __init__(self, *, keyword: SearchBackend, vector: SearchBackend) -> None:
        self.keyword = keyword
        self.vector = vector

    def search(
        self,
        keyword: str,
        *,
        mode: SearchMode = "HYBRID",
        limit: int = 20,
        effective_on: date | None = None,
        filters: dict[str, str] | None = None,
    ) -> list[SearchHit]:
        if not keyword.strip():
            raise ValueError("keyword is required")
        if mode not in {"KEYWORD", "VECTOR", "HYBRID"}:
            raise ValueError("unsupported search mode")
        bounded_limit = min(max(limit, 1), 20)
        basis_date = effective_on or date.today()
        query_filters = filters or {}
        if mode == "KEYWORD":
            raw = self.keyword.search(
                keyword, limit=20, effective_date=basis_date, filters=query_filters
            )
            return self._single(raw, "KEYWORD", bounded_limit)
        if mode == "VECTOR":
            raw = self.vector.search(
                keyword, limit=20, effective_date=basis_date, filters=query_filters
            )
            return self._single(raw, "VECTOR", bounded_limit)

        # Both calls are mandatory.  An exception from either is intentionally allowed
        # to escape instead of converting the other backend's hits into normal evidence.
        keyword_hits = self.keyword.search(
            keyword, limit=20, effective_date=basis_date, filters=query_filters
        )
        vector_hits = self.vector.search(
            keyword, limit=20, effective_date=basis_date, filters=query_filters
        )
        ranked: dict[str, list[tuple[BackendHit, SearchMode, int]]] = {}
        for rank, hit in enumerate(keyword_hits, 1):
            ranked.setdefault(hit.document.evidence_chunk_id, []).append((hit, "KEYWORD", rank))
        for rank, hit in enumerate(vector_hits, 1):
            ranked.setdefault(hit.document.evidence_chunk_id, []).append((hit, "VECTOR", rank))

        combined: list[SearchHit] = []
        for values in ranked.values():
            source_names = {source for _, source, _ in values}
            score = sum(1 / (_RRF_RANK_CONSTANT + rank) for _, _, rank in values)
            normalized_score = score / (2 / (_RRF_RANK_CONSTANT + 1))
            keyword_hit = next((hit for hit, source, _ in values if source == "KEYWORD"), None)
            preferred = keyword_hit or values[0][0]
            source: SearchMode = "HYBRID" if len(source_names) > 1 else values[0][1]
            combined.append(
                SearchHit(
                    preferred.document,
                    0,
                    round(normalized_score, 8),
                    source,
                    preferred.highlights,
                )
            )

        ordered = _preserve_search_source_coverage(
            sorted(combined, key=lambda hit: (-hit.relevance_score, hit.document.evidence_chunk_id))
        )[:bounded_limit]
        return [
            SearchHit(hit.document, rank, hit.relevance_score, hit.match_source, hit.highlights)
            for rank, hit in enumerate(ordered, 1)
        ]

    @staticmethod
    def _single(
        hits: Sequence[BackendHit], mode: Literal["KEYWORD", "VECTOR"], limit: int
    ) -> list[SearchHit]:
        return [
            SearchHit(hit.document, rank, round(hit.score, 8), mode, hit.highlights)
            for rank, hit in enumerate(hits[:limit], 1)
        ]

    @staticmethod
    def select_evidence(hits: Sequence[SearchHit]) -> list[SearchHit]:
        return list(hits[:5])

    @staticmethod
    def display_evidence(hits: Sequence[SearchHit]) -> list[SearchHit]:
        return list(hits[:3])


def _preserve_search_source_coverage(hits: list[SearchHit]) -> list[SearchHit]:
    """Avoid erasing the top semantic candidate when each backend found distinct chunks."""

    if any(hit.match_source == "HYBRID" for hit in hits):
        return hits
    keyword = next((hit for hit in hits if hit.match_source == "KEYWORD"), None)
    vector = next((hit for hit in hits if hit.match_source == "VECTOR"), None)
    if keyword is None or vector is None:
        return hits
    selected = [keyword, vector]
    return selected + [hit for hit in hits if hit not in selected]
