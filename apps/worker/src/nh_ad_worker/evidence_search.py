"""Read-only OpenSearch evidence retrieval for the live review worker.

The worker deliberately queries the same indexed evidence contract that the
backend writes during standard reindexing.  It does not silently fall back to
an unindexed database scan: an unavailable search service must remain visible
to the review result as ``SEARCH_UNAVAILABLE``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from math import isfinite
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from nh_ad_worker.results import EvidenceCandidate, EvidenceSearchFailure


Transport = Callable[[Request, float], bytes]


class OpenSearchEvidenceSearch:
    """Bounded keyword retrieval against the active standards index."""

    def __init__(
        self,
        endpoint: str,
        index: str,
        *,
        timeout_seconds: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        if not endpoint.strip() or not index.strip() or timeout_seconds <= 0:
            raise ValueError("OPENSEARCH_EVIDENCE_SEARCH_CONFIGURATION_INVALID")
        self._endpoint = endpoint.rstrip("/")
        self._index = index
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._send

    def __call__(self, query: str) -> tuple[EvidenceCandidate, ...]:
        if not query.strip():
            return ()
        today = datetime.now(UTC).date().isoformat()
        payload = {
            "size": 3,
            "query": {
                "bool": {
                    "must": [
                        {"multi_match": {"query": query, "fields": ["title^2", "chunk_text"]}}
                    ],
                    "filter": [
                        {"term": {"index_status": "ACTIVE"}},
                        {"term": {"is_active": True}},
                        {
                            "bool": {
                                "should": [
                                    {"bool": {"must_not": {"exists": {"field": "effective_date"}}}},
                                    {"range": {"effective_date": {"lte": today}}},
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                        {
                            "bool": {
                                "should": [
                                    {"bool": {"must_not": {"exists": {"field": "expired_date"}}}},
                                    {"range": {"expired_date": {"gte": today}}},
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                    ],
                }
            },
            "sort": [{"_score": "desc"}, {"evidence_chunk_id": "asc"}],
        }
        request = Request(
            f"{self._endpoint}/{quote(self._index)}/_search",
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
        if not isinstance(decoded, dict):
            raise EvidenceSearchFailure("RAG_SEARCH_FAILED")
        hits = decoded.get("hits", {})
        values = hits.get("hits", []) if isinstance(hits, dict) else []
        candidates: list[EvidenceCandidate] = []
        for hit in values:
            if not isinstance(hit, dict) or not isinstance(hit.get("_source"), dict):
                continue
            source: dict[str, Any] = hit["_source"]
            try:
                candidates.append(
                    EvidenceCandidate(
                        evidence_id=str(source["evidence_id"]),
                        standard_version_id=str(source["standard_version_id"]),
                        evidence_type=str(source["evidence_type"]),
                        title=str(source["title"]),
                        matched_text=str(source["chunk_text"]),
                        relevance_score=_bounded_keyword_score(hit.get("_score")),
                        # The persisted database contract intentionally uses a
                        # provider-neutral source vocabulary.  Keep the search
                        # engine implementation detail out of this field.
                        match_source="KEYWORD",
                        evidence_chunk_id=str(source["evidence_chunk_id"]),
                        article_no=(
                            str(source["article_no"]) if source.get("article_no") else None
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise EvidenceSearchFailure("RAG_SEARCH_FAILED") from exc
        return tuple(candidates)

    @staticmethod
    def _send(request: Request, timeout_seconds: float) -> bytes:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return cast(bytes, response.read())


def _bounded_keyword_score(value: object) -> float:
    """Map unbounded BM25 output into the persisted [0, 1] relevance contract."""

    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        raise ValueError("OPENSEARCH_SCORE_INVALID")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OPENSEARCH_SCORE_INVALID") from exc
    if not isfinite(score):
        raise ValueError("OPENSEARCH_SCORE_INVALID")
    if score <= 0:
        return 0.0
    return score / (score + 1.0)
