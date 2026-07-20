"""OpenAI-compatible vector query and hybrid evidence merge for live reviews."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from math import isfinite
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from nh_ad_ai_providers import EmbeddingProviderError, OpenAICompatibleEmbeddings

from nh_ad_worker.evidence_search import OpenSearchEvidenceSearch
from nh_ad_worker.results import EvidenceCandidate, EvidenceSearchFailure


Transport = Callable[[Request, float], bytes]
_RRF_RANK_CONSTANT = 60


class QdrantEvidenceSearch:
    """Read-only semantic evidence lookup using the configured embedding endpoint."""

    def __init__(
        self,
        endpoint: str,
        collection: str,
        embeddings: OpenAICompatibleEmbeddings,
        *,
        timeout_seconds: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        if not endpoint.strip() or not collection.strip() or timeout_seconds <= 0:
            raise ValueError("QDRANT_EVIDENCE_SEARCH_CONFIGURATION_INVALID")
        self._endpoint = endpoint.rstrip("/")
        self._collection = collection
        self._embeddings = embeddings
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._send

    def __call__(self, query: str) -> tuple[EvidenceCandidate, ...]:
        try:
            vector = self._embeddings.embed([query])[0]
        except (EmbeddingProviderError, ValueError) as exc:
            raise EvidenceSearchFailure("RAG_SEARCH_UNAVAILABLE") from exc
        today = datetime.now(UTC).date().isoformat()
        payload = {
            "vector": list(vector),
            "limit": 20,
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "index_status", "match": {"value": "ACTIVE"}},
                    {"key": "is_active", "match": {"value": True}},
                ]
            },
        }
        request = Request(
            f"{self._endpoint}/collections/{quote(self._collection)}/points/search",
            data=json.dumps(payload, separators=(",", ":")).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            raw = self._transport(request, self._timeout_seconds)
            decoded = json.loads(raw)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise EvidenceSearchFailure("RAG_SEARCH_UNAVAILABLE") from exc
        if not isinstance(decoded, dict) or not isinstance(decoded.get("result"), list):
            raise EvidenceSearchFailure("RAG_SEARCH_FAILED")
        candidates: list[EvidenceCandidate] = []
        for hit in decoded["result"]:
            if not isinstance(hit, dict) or not isinstance(hit.get("payload"), dict):
                continue
            source: dict[str, Any] = hit["payload"]
            if not _is_effective(source, today):
                continue
            try:
                candidates.append(
                    _candidate(source, _bounded_vector_score(hit.get("score")), "QDRANT_VECTOR")
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise EvidenceSearchFailure("RAG_SEARCH_FAILED") from exc
        return tuple(candidates)

    @staticmethod
    def _send(request: Request, timeout_seconds: float) -> bytes:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return cast(bytes, response.read())


class HybridEvidenceSearch:
    """Require both search backends and fuse their ranked results without score comparison."""

    def __init__(self, *, keyword: OpenSearchEvidenceSearch, vector: QdrantEvidenceSearch) -> None:
        self._keyword = keyword
        self._vector = vector

    def __call__(self, query: str) -> tuple[EvidenceCandidate, ...]:
        keyword_hits = self._keyword(query)
        vector_hits = self._vector(query)
        ranked: dict[str, list[tuple[EvidenceCandidate, int]]] = {}
        for rank, hit in enumerate(keyword_hits, 1):
            ranked.setdefault(hit.evidence_chunk_id or hit.evidence_id, []).append((hit, rank))
        for rank, hit in enumerate(vector_hits, 1):
            ranked.setdefault(hit.evidence_chunk_id or hit.evidence_id, []).append((hit, rank))

        fused: list[EvidenceCandidate] = []
        for values in ranked.values():
            source_names = {candidate.match_source for candidate, _ in values}
            # The backend scores have unrelated distributions (BM25 versus cosine).
            # Normalize reciprocal-rank fusion to 0..1 instead of comparing those
            # source scores directly. A first-ranked result from one backend is 0.5;
            # the same result from both backends can reach 1.0.
            score = sum(1 / (_RRF_RANK_CONSTANT + rank) for _, rank in values)
            normalized_score = score / (2 / (_RRF_RANK_CONSTANT + 1))
            preferred = next(
                (candidate for candidate, _ in values if candidate.match_source == "KEYWORD"),
                values[0][0],
            )
            fused.append(
                replace(
                    preferred,
                    relevance_score=round(normalized_score, 8),
                    match_source="HYBRID" if len(source_names) > 1 else preferred.match_source,
                )
            )

        ordered = sorted(fused, key=lambda hit: (-hit.relevance_score, hit.evidence_chunk_id or ""))
        return tuple(_preserve_source_coverage(ordered)[:3])


def _preserve_source_coverage(hits: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
    """Keep the best semantic hit visible when both backends returned distinct chunks."""

    if any(hit.match_source == "HYBRID" for hit in hits):
        return hits
    keyword = next((hit for hit in hits if hit.match_source == "KEYWORD"), None)
    vector = next((hit for hit in hits if hit.match_source == "VECTOR"), None)
    if keyword is None or vector is None:
        return hits
    selected = [keyword, vector]
    return selected + [hit for hit in hits if hit not in selected]


def _candidate(source: dict[str, Any], score: float, source_name: str) -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id=str(source["evidence_id"]),
        standard_version_id=str(source["standard_version_id"]),
        evidence_type=str(source["evidence_type"]),
        title=str(source["title"]),
        matched_text=str(source["chunk_text"]),
        relevance_score=score,
        # ``review_item_evidences.match_source`` is a closed, provider-neutral
        # database contract (KEYWORD/VECTOR/HYBRID/RULE_METADATA).
        match_source="VECTOR" if source_name == "QDRANT_VECTOR" else source_name,
        evidence_chunk_id=str(source["evidence_chunk_id"]),
        article_no=str(source["article_no"]) if source.get("article_no") else None,
    )


def _is_effective(source: dict[str, Any], today: str) -> bool:
    effective = source.get("effective_date")
    expired = source.get("expired_date")
    return (effective is None or str(effective) <= today) and (
        expired is None or str(expired) >= today
    )


def _bounded_vector_score(value: object) -> float:
    """Protect the [0, 1] persistence contract from a non-positive cosine hit."""

    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        raise EvidenceSearchFailure("RAG_SEARCH_FAILED")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceSearchFailure("RAG_SEARCH_FAILED") from exc
    if not isfinite(score):
        raise EvidenceSearchFailure("RAG_SEARCH_FAILED")
    return min(max(score, 0.0), 1.0)
