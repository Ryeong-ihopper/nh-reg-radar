import json
from urllib.error import URLError
from urllib.request import Request

import pytest

from nh_ad_worker.evidence_search import OpenSearchEvidenceSearch
from nh_ad_worker.results import EvidenceSearchFailure


def test_live_evidence_search_uses_active_opensearch_contract() -> None:
    captured: dict[str, object] = {}

    def transport(request: Request, timeout: float) -> bytes:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return json.dumps(
            {
                "hits": {
                    "hits": [
                        {
                            "_score": 1.3,
                            "_source": {
                                "evidence_id": "EVD-1",
                                "standard_version_id": "STDVER-1",
                                "evidence_type": "REGULATION",
                                "title": "금리 광고 기준",
                                "chunk_text": "금리 조건을 표시한다.",
                                "evidence_chunk_id": "CHUNK-1",
                                "article_no": "1",
                            },
                        }
                    ]
                }
            }
        ).encode()

    result = OpenSearchEvidenceSearch(
        "http://search.invalid:9200", "reference-docs", timeout_seconds=7, transport=transport
    )("우대 금리")

    assert captured["url"] == "http://search.invalid:9200/reference-docs/_search"
    assert captured["timeout"] == 7
    payload = captured["payload"]
    assert isinstance(payload, dict)
    filters = payload["query"]["bool"]["filter"]  # type: ignore[index]
    assert {"term": {"index_status": "ACTIVE"}} in filters
    assert result[0].match_source == "OPENSEARCH_KEYWORD"
    assert result[0].evidence_chunk_id == "CHUNK-1"


def test_live_evidence_search_fails_closed_when_opensearch_is_unavailable() -> None:
    def unavailable(_request: Request, _timeout: float) -> bytes:
        raise URLError("offline")

    search = OpenSearchEvidenceSearch(
        "http://search.invalid:9200", "reference-docs", transport=unavailable
    )

    with pytest.raises(EvidenceSearchFailure, match="RAG_SEARCH_UNAVAILABLE"):
        search("금리")
