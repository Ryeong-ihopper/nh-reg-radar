from datetime import UTC, date, datetime

import pytest

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.search import HybridSearch, InMemorySearchBackend
from nh_ad_backend.standards import InMemoryStandardRepository, StandardService, StandardsError


NOW = datetime(2026, 7, 14, 6, 0, tzinfo=UTC)
MANAGER = CurrentUser(
    "standard",
    "기준담당",
    "DPT-C",
    "준법부",
    ("STANDARD_MANAGER",),
    1,
)
PRODUCT_USER = CurrentUser(
    "product",
    "상품담당",
    "DPT-A",
    "상품부",
    ("PRODUCT_DEPARTMENT_USER",),
    1,
)


def service() -> tuple[StandardService, InMemoryStandardRepository]:
    repository = InMemoryStandardRepository()
    counter = iter(range(1, 100))
    search = HybridSearch(
        keyword=InMemorySearchBackend("OPENSEARCH"),
        vector=InMemorySearchBackend("QDRANT"),
    )
    return (
        StandardService(
            repository,
            search,
            now=lambda: NOW,
            identifier=lambda prefix: f"{prefix}-{next(counter):04d}",
            environment="test",
        ),
        repository,
    )


def internal_metadata() -> dict[str, object]:
    return {
        "owningDepartment": "준법부",
        "documentName": "광고심의 내규",
        "sectionPath": "표현/금지",
        "effectiveDate": "2026-01-01",
        "version": "1.0",
        "productGroup": "SAVINGS",
    }


def create(service: StandardService, *, effective_on: date = date(2026, 1, 1)):
    return service.create(
        MANAGER,
        title="광고심의 내규",
        evidence_type="INTERNAL_STANDARD",
        product_group="SAVINGS",
        advertisement_type="MOBILE_BANNER",
        rule_type="PROHIBITED",
        importance="HIGH",
        effective_date=effective_on,
        expired_date=None,
        metadata=internal_metadata(),
        content="객관적 근거 없는 최고 표현을 금지한다.\n\n금리 조건을 명확하게 표시한다.",
        trace_id="req-create",
    )


def test_metadata_authorization_and_immutable_version_selection() -> None:
    standards, repository = service()
    with pytest.raises(StandardsError) as denied:
        standards.create(
            PRODUCT_USER,
            title="x",
            evidence_type="INTERNAL_STANDARD",
            product_group="SAVINGS",
            advertisement_type=None,
            rule_type="REFERENCE",
            importance="LOW",
            effective_date=date(2026, 1, 1),
            expired_date=None,
            metadata=internal_metadata(),
            content="본문",
            trace_id="req-denied",
        )
    assert denied.value.status_code == 403

    invalid = internal_metadata()
    invalid.pop("sectionPath")
    with pytest.raises(StandardsError) as missing:
        standards.create(
            MANAGER,
            title="x",
            evidence_type="INTERNAL_STANDARD",
            product_group="SAVINGS",
            advertisement_type=None,
            rule_type="REFERENCE",
            importance="LOW",
            effective_date=date(2026, 1, 1),
            expired_date=None,
            metadata=invalid,
            content="본문",
            trace_id="req-invalid",
        )
    assert missing.value.code == "REFERENCE_METADATA_INVALID"

    created = create(standards)
    updated = standards.update(
        MANAGER,
        created.standard_id,
        title="광고심의 내규 개정",
        content="개정된 최고 표현 기준",
        effective_date=date(2026, 7, 1),
        expired_date=None,
        metadata=internal_metadata(),
        change_reason="정기 개정",
        trace_id="req-update",
    )
    assert created.standard_version_id != updated.standard_version_id
    assert [item.version for item in repository.histories(created.standard_id)] == ["2.0", "1.0"]
    assert standards.version_on(created.standard_id, date(2026, 6, 30)).version == "1.0"
    assert standards.version_on(created.standard_id, date(2026, 7, 1)).version == "2.0"


def test_reindex_is_idempotent_and_deactivation_excludes_search() -> None:
    standards, repository = service()
    created = create(standards)
    first = standards.reindex(
        MANAGER,
        created.standard_id,
        created.standard_version_id,
        reindex_scope="INDEX_ONLY",
        reason="fixture",
        embedding_model="fixed-v1",
        chunking_policy_version="reference-chunking-v1",
        search_schema_version="search-schema-v1",
        opensearch_analyzer_version="ko-v1",
        synonym_version="syn-v1",
        trace_id="req-index-1",
    )
    second = standards.reindex(
        MANAGER,
        created.standard_id,
        created.standard_version_id,
        reindex_scope="INDEX_ONLY",
        reason="retry",
        embedding_model="fixed-v1",
        chunking_policy_version="reference-chunking-v1",
        search_schema_version="search-schema-v1",
        opensearch_analyzer_version="ko-v2",
        synonym_version="syn-v2",
        trace_id="req-index-2",
    )
    assert first.job_status == second.job_status == "SUCCEEDED"
    assert len(repository.chunks_for_version(created.standard_version_id)) == 2
    assert len({chunk.deterministic_index_id for chunk in repository.chunks}) == 2
    assert {chunk.opensearch_analyzer_version for chunk in repository.chunks} == {"ko-v2"}
    assert {chunk.synonym_version for chunk in repository.chunks} == {"syn-v2"}
    assert standards.search("최고", mode="KEYWORD")[0].document.standard_id == created.standard_id

    standards.deactivate(MANAGER, created.standard_id, reason="대체", trace_id="req-off")
    assert standards.search("최고", mode="KEYWORD") == []
