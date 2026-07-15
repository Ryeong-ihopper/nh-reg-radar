"""Opt-in actual PostgreSQL/Qdrant/OpenSearch M3 vertical.

Set M3_LIVE_DATABASE_URL, M3_LIVE_QDRANT_URL, and M3_LIVE_OPENSEARCH_URL after
applying migrations and synthetic M3 seeds. The normal test gate skips explicitly.
"""

import os
from datetime import date

import pytest
from sqlalchemy import create_engine

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.search import HybridSearch
from nh_ad_backend.search_http import OpenSearchBackend, QdrantBackend
from nh_ad_backend.standards import StandardService
from nh_ad_backend.standards_postgres import PostgresStandardRepository


def test_actual_postgres_qdrant_opensearch_vertical() -> None:
    database_url = os.getenv("M3_LIVE_DATABASE_URL")
    qdrant_url = os.getenv("M3_LIVE_QDRANT_URL")
    opensearch_url = os.getenv("M3_LIVE_OPENSEARCH_URL")
    if not all((database_url, qdrant_url, opensearch_url)):
        pytest.skip("set M3_LIVE_DATABASE_URL/QDRANT_URL/OPENSEARCH_URL for live tri-store")
    assert database_url and qdrant_url and opensearch_url

    repository = PostgresStandardRepository(create_engine(database_url, pool_pre_ping=True))
    search = HybridSearch(
        keyword=OpenSearchBackend(
            opensearch_url,
            "m3_live_evidence",
            environment="test",
            embedding_model="fixed-fixture-v1",
            chunking_policy_version="reference-chunking-v1",
        ),
        vector=QdrantBackend(
            qdrant_url,
            "m3_live_evidence",
            environment="test",
            embedding_model="fixed-fixture-v1",
            chunking_policy_version="reference-chunking-v1",
            dimensions=3,
            document_vector=lambda _document: [0.1, 0.2, 0.3],
            query_vector=lambda _keyword: [0.1, 0.2, 0.3],
        ),
    )
    service = StandardService(repository, search, environment="test")
    actor = CurrentUser(
        "USR-SYNTH-COMPLIANCE",
        "Synthetic Manager",
        "DPT-SYNTH-COMPLIANCE",
        "Synthetic Compliance Team",
        ("STANDARD_MANAGER",),
        1,
    )

    job = service.reindex(
        actor,
        "STD-SYNTH-0001",
        "STDVER-SYNTH-0001",
        reindex_scope="CHUNK_AND_INDEX",
        reason="opt-in live tri-store",
        embedding_model="fixed-fixture-v1",
        chunking_policy_version="reference-chunking-v1",
        search_schema_version="search-schema-v1",
        opensearch_analyzer_version="ko-analyzer-v1",
        synonym_version="synonym-v1",
        target_indexes=("QDRANT", "OPENSEARCH"),
        trace_id="trace-live-tristore",
    )
    hits = service.search("required notice", mode="HYBRID", effective_on=date(2026, 7, 14))

    assert job.job_status == "SUCCEEDED"
    assert job.qdrant_status == job.opensearch_status == "ACTIVE"
    assert hits and hits[0].document.evidence_chunk_id == "ECH-SYNTH-0001"
    assert repository.get_reindex_job(job.job_id).job_status == "SUCCEEDED"  # type: ignore[union-attr]
