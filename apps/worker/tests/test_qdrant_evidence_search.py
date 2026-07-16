import json
from urllib.request import Request

from nh_ad_ai_providers import OpenAICompatibleEmbeddings

from nh_ad_worker.evidence_search import OpenSearchEvidenceSearch
from nh_ad_worker.qdrant_evidence_search import HybridEvidenceSearch, QdrantEvidenceSearch


def embeddings() -> OpenAICompatibleEmbeddings:
    return OpenAICompatibleEmbeddings(
        api_key="secret",
        model="embedding-model",
        base_url="https://provider.invalid/v1",
        dimensions=2,
        transport=lambda _request, _timeout: b'{"data":[{"index":0,"embedding":[0.1,0.2]}]}',
    )


def payload(chunk_id: str) -> dict[str, object]:
    return {
        "evidence_id": "EVD-1",
        "standard_version_id": "STDVER-1",
        "evidence_type": "REGULATION",
        "title": "금리 광고 기준",
        "chunk_text": "금리 조건을 표시한다.",
        "evidence_chunk_id": chunk_id,
        "article_no": "1",
        "index_status": "ACTIVE",
        "is_active": True,
    }


def test_qdrant_vector_query_uses_openai_compatible_embedding() -> None:
    captured: dict[str, object] = {}

    def transport(request: Request, _timeout: float) -> bytes:
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data or b"{}")
        return json.dumps({"result": [{"score": 0.93, "payload": payload("CHUNK-1")}]}).encode()

    result = QdrantEvidenceSearch(
        "http://qdrant.invalid:6333", "reference-v2", embeddings(), transport=transport
    )("우대 금리")

    assert captured["url"] == "http://qdrant.invalid:6333/collections/reference-v2/points/search"
    assert captured["payload"]["vector"] == [0.1, 0.2]  # type: ignore[index]
    assert result[0].relevance_score == 0.93
    assert result[0].match_source == "VECTOR"


def test_qdrant_vector_scores_are_bounded_for_persistence() -> None:
    result = QdrantEvidenceSearch(
        "http://qdrant.invalid:6333",
        "reference-v2",
        embeddings(),
        transport=lambda _request, _timeout: json.dumps(
            {"result": [{"score": -0.2, "payload": payload("CHUNK-1")}]}
        ).encode(),
    )("금리")

    assert result[0].relevance_score == 0.0


def test_hybrid_search_requires_and_merges_keyword_and_vector_hits() -> None:
    keyword = OpenSearchEvidenceSearch(
        "http://opensearch.invalid:9200",
        "reference-v2",
        transport=lambda _request, _timeout: json.dumps(
            {"hits": {"hits": [{"_score": 0.8, "_source": payload("CHUNK-1")}]}}
        ).encode(),
    )
    vector = QdrantEvidenceSearch(
        "http://qdrant.invalid:6333",
        "reference-v2",
        embeddings(),
        transport=lambda _request, _timeout: json.dumps(
            {"result": [{"score": 0.93, "payload": payload("CHUNK-1")}]}
        ).encode(),
    )

    result = HybridEvidenceSearch(keyword=keyword, vector=vector)("금리")

    assert len(result) == 1
    assert result[0].match_source == "HYBRID"
    assert result[0].relevance_score == 0.93
