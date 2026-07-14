"""Dependency-free Qdrant and OpenSearch adapters for bounded M3 evidence tests."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from nh_ad_backend.search import (
    BackendHit,
    SearchDocument,
    SearchInfrastructureError,
    deterministic_index_id,
)


JsonObject = dict[str, Any]


def _request(
    backend: str,
    method: str,
    url: str,
    body: object | None = None,
    *,
    content_type: str = "application/json",
    accepted: tuple[int, ...] = (200, 201),
) -> JsonObject:
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    request = Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", content_type)
    try:
        # First-time collection/index creation can legitimately exceed five seconds on
        # a cold local node. Keep the request bounded without misclassifying startup
        # work as an infrastructure outage.
        with urlopen(request, timeout=30) as response:  # noqa: S310 - configured private service URL
            raw = response.read()
            if response.status not in accepted:
                raise SearchInfrastructureError(backend, f"HTTP {response.status}")
    except HTTPError as exc:
        if exc.code in accepted:
            raw = exc.read()
        else:
            raise SearchInfrastructureError(backend, f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SearchInfrastructureError(backend, str(exc)) from exc
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SearchInfrastructureError(backend, "invalid JSON response") from exc
    if not isinstance(decoded, dict):
        raise SearchInfrastructureError(backend, "invalid response object")
    return decoded


def _payload(document: SearchDocument) -> JsonObject:
    return {
        "evidence_chunk_id": document.evidence_chunk_id,
        "evidence_id": document.evidence_id,
        "standard_id": document.standard_id,
        "standard_version_id": document.standard_version_id,
        "evidence_type": document.evidence_type,
        "title": document.title,
        "chunk_text": document.chunk_text,
        "article_no": document.article_no,
        "section_path": document.section_path,
        "product_group": document.product_group,
        "advertisement_type": document.advertisement_type,
        "rule_type": document.rule_type,
        "importance": document.importance,
        "effective_date": document.effective_date.isoformat() if document.effective_date else None,
        "expired_date": document.expired_date.isoformat() if document.expired_date else None,
        "version": document.version,
        "index_status": "ACTIVE" if document.is_active else "EXCLUDED",
        "is_active": document.is_active,
        "opensearch_analyzer_version": document.opensearch_analyzer_version,
        "synonym_version": document.synonym_version,
    }


def _document(payload: JsonObject) -> SearchDocument:
    return SearchDocument(
        evidence_chunk_id=str(payload["evidence_chunk_id"]),
        evidence_id=str(payload["evidence_id"]),
        standard_id=str(payload["standard_id"]),
        standard_version_id=str(payload["standard_version_id"]),
        evidence_type=str(payload["evidence_type"]),
        title=str(payload["title"]),
        chunk_text=str(payload["chunk_text"]),
        article_no=_optional_text(payload.get("article_no")),
        section_path=_optional_text(payload.get("section_path")),
        product_group=_optional_text(payload.get("product_group")),
        advertisement_type=_optional_text(payload.get("advertisement_type")),
        rule_type=str(payload["rule_type"]),
        importance=str(payload.get("importance") or "MEDIUM"),
        effective_date=_optional_date(payload.get("effective_date")),
        expired_date=_optional_date(payload.get("expired_date")),
        version=str(payload["version"]),
        is_active=bool(payload.get("is_active", True)),
        opensearch_analyzer_version=_optional_text(payload.get("opensearch_analyzer_version")),
        synonym_version=_optional_text(payload.get("synonym_version")),
    )


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value is not None else None


class OpenSearchBackend:
    name = "OPENSEARCH"

    def __init__(
        self,
        endpoint: str,
        index: str,
        *,
        environment: str,
        embedding_model: str,
        chunking_policy_version: str,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._index = index
        self._environment = environment
        self._embedding_model = embedding_model
        self._chunking_policy_version = chunking_policy_version

    def ensure_index(self) -> None:
        mapping = {
            "settings": {
                "analysis": {
                    "filter": {
                        "m3_synonyms": {
                            "type": "synonym_graph",
                            "synonyms": ["우대금리, 특별금리", "최고, 최대"],
                        }
                    },
                    "analyzer": {
                        "m3_korean": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "m3_synonyms"],
                        }
                    },
                }
            },
            "mappings": {
                "properties": {
                    "title": {
                        "type": "text",
                        "analyzer": "m3_korean",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "chunk_text": {"type": "text", "analyzer": "m3_korean"},
                    "article_no": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "effective_date": {"type": "date"},
                    "expired_date": {"type": "date"},
                    **{
                        field: {"type": "keyword"}
                        for field in (
                            "evidence_chunk_id",
                            "evidence_id",
                            "standard_id",
                            "standard_version_id",
                            "evidence_type",
                            "product_group",
                            "advertisement_type",
                            "rule_type",
                            "importance",
                            "index_status",
                            "opensearch_analyzer_version",
                            "synonym_version",
                        )
                    },
                    "is_active": {"type": "boolean"},
                }
            },
        }
        _request(
            self.name,
            "PUT",
            f"{self._endpoint}/{quote(self._index)}",
            mapping,
            accepted=(200, 201, 400),
        )

    def upsert(self, documents: Sequence[SearchDocument]) -> None:
        self.ensure_index()
        lines: list[str] = []
        for document in documents:
            logical_id = deterministic_index_id(
                self._environment,
                document.standard_version_id,
                document.evidence_chunk_id,
                self._embedding_model,
                self._chunking_policy_version,
            )
            lines.append(json.dumps({"index": {"_index": self._index, "_id": logical_id}}))
            lines.append(json.dumps(_payload(document), ensure_ascii=False))
        if not lines:
            return
        result = _request(
            self.name,
            "POST",
            f"{self._endpoint}/_bulk?refresh=true",
            ("\n".join(lines) + "\n").encode("utf-8"),
            content_type="application/x-ndjson",
        )
        if result.get("errors") is True:
            raise SearchInfrastructureError(self.name, "bulk upsert partially failed")

    def exclude(self, standard_id: str) -> None:
        _request(
            self.name,
            "POST",
            f"{self._endpoint}/{quote(self._index)}/_update_by_query?refresh=true",
            {
                "query": {"term": {"standard_id": standard_id}},
                "script": {
                    "source": "ctx._source.index_status='EXCLUDED'; ctx._source.is_active=false"
                },
            },
            accepted=(200, 404),
        )

    def search(
        self,
        keyword: str,
        *,
        limit: int,
        effective_date: date,
        filters: dict[str, str],
    ) -> list[BackendHit]:
        must = [{"multi_match": {"query": keyword, "fields": ["title^2", "chunk_text"]}}]
        clauses: list[JsonObject] = [
            {"term": {"index_status": "ACTIVE"}},
            {"term": {"is_active": True}},
            {
                "bool": {
                    "should": [
                        {"bool": {"must_not": {"exists": {"field": "effective_date"}}}},
                        {"range": {"effective_date": {"lte": effective_date.isoformat()}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            {
                "bool": {
                    "should": [
                        {"bool": {"must_not": {"exists": {"field": "expired_date"}}}},
                        {"range": {"expired_date": {"gte": effective_date.isoformat()}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            *({"term": {field: value}} for field, value in filters.items()),
        ]
        result = _request(
            self.name,
            "POST",
            f"{self._endpoint}/{quote(self._index)}/_search",
            {
                "size": min(limit, 20),
                "query": {"bool": {"must": must, "filter": clauses}},
                "sort": [{"_score": "desc"}, {"evidence_chunk_id": "asc"}],
                "highlight": {"fields": {"title": {}, "chunk_text": {}}},
            },
        )
        hits = result.get("hits", {}).get("hits", [])
        return [
            BackendHit(
                _document(item["_source"]),
                float(item.get("_score") or 0.0),
                {
                    str(field): [str(fragment) for fragment in fragments]
                    for field, fragments in item.get("highlight", {}).items()
                    if isinstance(fragments, list)
                },
            )
            for item in hits
            if isinstance(item, dict) and isinstance(item.get("_source"), dict)
        ]


class QdrantBackend:
    name = "QDRANT"

    def __init__(
        self,
        endpoint: str,
        collection: str,
        *,
        environment: str,
        embedding_model: str,
        chunking_policy_version: str,
        dimensions: int,
        document_vector: Callable[[SearchDocument], Sequence[float]],
        query_vector: Callable[[str], Sequence[float]],
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._collection = collection
        self._environment = environment
        self._embedding_model = embedding_model
        self._chunking_policy_version = chunking_policy_version
        self._dimensions = dimensions
        self._document_vector = document_vector
        self._query_vector = query_vector

    def ensure_collection(self) -> None:
        _request(
            self.name,
            "PUT",
            f"{self._endpoint}/collections/{quote(self._collection)}",
            {"vectors": {"size": self._dimensions, "distance": "Cosine"}},
            accepted=(200, 201, 409),
        )

    def upsert(self, documents: Sequence[SearchDocument]) -> None:
        self.ensure_collection()
        points = []
        for document in documents:
            logical_id = deterministic_index_id(
                self._environment,
                document.standard_version_id,
                document.evidence_chunk_id,
                self._embedding_model,
                self._chunking_policy_version,
            )
            vector = list(self._document_vector(document))
            if len(vector) != self._dimensions:
                raise ValueError("fixed document vector dimension mismatch")
            payload: JsonObject = _payload(document)
            payload["deterministic_index_id"] = logical_id
            points.append(
                {
                    "id": str(uuid5(NAMESPACE_URL, logical_id)),
                    "vector": vector,
                    "payload": payload,
                }
            )
        if points:
            _request(
                self.name,
                "PUT",
                f"{self._endpoint}/collections/{quote(self._collection)}/points?wait=true",
                {"points": points},
            )

    def exclude(self, standard_id: str) -> None:
        _request(
            self.name,
            "POST",
            f"{self._endpoint}/collections/{quote(self._collection)}/points/payload?wait=true",
            {
                "payload": {"index_status": "EXCLUDED", "is_active": False},
                "filter": {"must": [{"key": "standard_id", "match": {"value": standard_id}}]},
            },
            accepted=(200, 404),
        )

    def search(
        self,
        keyword: str,
        *,
        limit: int,
        effective_date: date,
        filters: dict[str, str],
    ) -> list[BackendHit]:
        vector = list(self._query_vector(keyword))
        if len(vector) != self._dimensions:
            raise ValueError("fixed query vector dimension mismatch")
        must: list[JsonObject] = [
            {"key": "index_status", "match": {"value": "ACTIVE"}},
            {"key": "is_active", "match": {"value": True}},
            *({"key": field, "match": {"value": value}} for field, value in filters.items()),
        ]
        result = _request(
            self.name,
            "POST",
            f"{self._endpoint}/collections/{quote(self._collection)}/points/search",
            {
                "vector": vector,
                "limit": min(limit, 20),
                "with_payload": True,
                "filter": {"must": must},
            },
        )
        values = result.get("result", [])
        hits = [
            BackendHit(_document(item["payload"]), float(item.get("score") or 0.0))
            for item in values
            if isinstance(item, dict) and isinstance(item.get("payload"), dict)
        ]
        return [
            hit
            for hit in hits
            if (
                hit.document.effective_date is None or hit.document.effective_date <= effective_date
            )
            and (hit.document.expired_date is None or hit.document.expired_date >= effective_date)
        ]
