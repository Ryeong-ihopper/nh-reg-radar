from datetime import date

import pytest

import nh_ad_backend.search_http as search_http
from nh_ad_backend.main import fixed_fixture_vector, unavailable_production_vector
from nh_ad_backend.search import SearchDocument, SearchInfrastructureError
from nh_ad_backend.search_http import OpenSearchBackend


def document() -> SearchDocument:
    return SearchDocument(
        "ECH-TEST",
        "EVD-TEST",
        "STD-TEST",
        "STDVER-TEST",
        "INTERNAL_STANDARD",
        "우대금리 안내",
        "최고 우대금리를 안내한다.",
        None,
        "1",
        "SAVINGS",
        "MOBILE_BANNER",
        "REQUIRED",
        "HIGH",
        date(2026, 1, 1),
        None,
        "1.0",
        True,
        "ko-analyzer-v2",
        "synonym-v2",
    )


def test_dev_test_vector_is_fixed_and_production_remains_fail_closed() -> None:
    assert fixed_fixture_vector(document()) == [0.1, 0.2, 0.3]
    assert fixed_fixture_vector("same fixture") == [0.1, 0.2, 0.3]
    with pytest.raises(SearchInfrastructureError, match="production embedding provider"):
        unavailable_production_vector("query")


def test_opensearch_analyzer_synonym_metadata_and_highlights(monkeypatch) -> None:
    calls: list[tuple[str, str, object | None]] = []

    def fake_request(backend, method, url, body=None, **_kwargs):
        calls.append((method, url, body))
        if url.endswith("/_search"):
            return {
                "hits": {
                    "hits": [
                        {
                            "_score": 2.0,
                            "_source": search_http._payload(document()),
                            "highlight": {
                                "title": ["<em>우대금리</em> 안내"],
                                "chunk_text": ["최고 <em>우대금리</em>를 안내한다."],
                            },
                        }
                    ]
                }
            }
        return {"errors": False}

    monkeypatch.setattr(search_http, "_request", fake_request)
    backend = OpenSearchBackend(
        "http://opensearch:9200",
        "test-index",
        environment="test",
        embedding_model="fixed-fixture-v1",
        chunking_policy_version="reference-chunking-v1",
    )

    backend.upsert([document()])
    hits = backend.search("특별금리", limit=20, effective_date=date(2026, 7, 14), filters={})

    mapping = calls[0][2]
    assert isinstance(mapping, dict)
    assert mapping["settings"]["analysis"]["filter"]["m3_synonyms"]["type"] == "synonym_graph"
    bulk = calls[1][2]
    assert isinstance(bulk, bytes)
    assert b'"opensearch_analyzer_version": "ko-analyzer-v2"' in bulk
    assert b'"synonym_version": "synonym-v2"' in bulk
    assert hits[0].highlights["title"] == ["<em>우대금리</em> 안내"]
    search_body = calls[2][2]
    assert isinstance(search_body, dict)
    assert set(search_body["highlight"]["fields"]) == {"title", "chunk_text"}
