from datetime import date

import pytest

from nh_ad_backend.search import (
    HybridSearch,
    InMemorySearchBackend,
    SearchDocument,
    SearchInfrastructureError,
    deterministic_index_id,
    direct_text_chunks,
)


def document(identifier: str, *, importance: str = "MEDIUM") -> SearchDocument:
    return SearchDocument(
        evidence_chunk_id=identifier,
        evidence_id=f"EVD-{identifier}",
        standard_id="STD-1",
        standard_version_id="STDVER-1",
        evidence_type="INTERNAL_STANDARD",
        title="광고 심의 기준",
        chunk_text=f"{identifier} 최고 금리 표현",
        article_no=None,
        section_path=None,
        product_group="SAVINGS",
        advertisement_type="MOBILE_BANNER",
        rule_type="PROHIBITED",
        importance=importance,
        effective_date=date(2026, 1, 1),
        expired_date=None,
        version="1.0",
    )


def test_direct_text_chunk_and_index_ids_are_repeatable() -> None:
    first = direct_text_chunks(
        "STDVER-1",
        "첫 번째 직접 입력 문단입니다.\n\n두 번째 직접 입력 문단입니다.",
        max_characters=30,
    )
    second = direct_text_chunks(
        "STDVER-1",
        "첫 번째 직접 입력 문단입니다.\n\n두 번째 직접 입력 문단입니다.",
        max_characters=30,
    )
    assert first == second
    assert [chunk.chunk_no for chunk in first] == [1, 2]
    assert len({chunk.evidence_chunk_id for chunk in first}) == 2
    assert deterministic_index_id(
        "dev", "STDVER-1", first[0].evidence_chunk_id, "fixed-v1", "chunk-v1"
    ) == deterministic_index_id(
        "dev", "STDVER-1", first[0].evidence_chunk_id, "fixed-v1", "chunk-v1"
    )


def test_hybrid_search_is_deterministic_and_never_silently_falls_back() -> None:
    values = [document("ECH-A"), document("ECH-B", importance="HIGH"), document("ECH-C")]
    keyword = InMemorySearchBackend("OPENSEARCH")
    vector = InMemorySearchBackend("QDRANT")
    keyword.replace(values, {"ECH-A": 0.9, "ECH-B": 0.8, "ECH-C": 0.7})
    vector.replace(values, {"ECH-B": 0.9, "ECH-A": 0.8, "ECH-C": 0.7})
    search = HybridSearch(keyword=keyword, vector=vector)

    first = search.search("최고 금리", mode="HYBRID", limit=20)
    second = search.search("최고 금리", mode="HYBRID", limit=20)
    assert first == second
    assert [hit.document.evidence_chunk_id for hit in first] == ["ECH-A", "ECH-B", "ECH-C"]
    assert [hit.rank_no for hit in first] == [1, 2, 3]
    assert all(hit.match_source == "HYBRID" for hit in first)

    vector.fail_next = True
    with pytest.raises(SearchInfrastructureError, match="QDRANT"):
        search.search("최고 금리", mode="HYBRID", limit=20)


def test_top_20_candidates_top_5_evidence_and_top_3_display() -> None:
    values = [document(f"ECH-{index:02d}") for index in range(25)]
    keyword = InMemorySearchBackend("OPENSEARCH")
    vector = InMemorySearchBackend("QDRANT")
    scores = {value.evidence_chunk_id: 1 - index / 100 for index, value in enumerate(values)}
    keyword.replace(values, scores)
    vector.replace(values, scores)
    search = HybridSearch(keyword=keyword, vector=vector)

    candidates = search.search("표현", mode="HYBRID", limit=20)
    assert len(candidates) == 20
    assert len(search.select_evidence(candidates)) == 5
    assert len(search.display_evidence(candidates)) == 3
