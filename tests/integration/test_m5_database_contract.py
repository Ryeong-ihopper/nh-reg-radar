from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "apps"
    / "backend"
    / "migrations"
    / "versions"
    / "0005_m5_review_results.py"
)


def test_m5_migration_is_additive_and_owns_result_tables() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision: str | None = "0004_m4_parser_ocr_jobs"' in source
    for table in ("review_items", "review_item_evidences", "annotations"):
        assert f'"{table}"' in source
    for prior_revision in (
        "0001_schema_only_base",
        "0002_m2_auth_advertisement_audit",
        "0003_m3_standards_search",
        "0004_m4_parser_ocr_jobs",
    ):
        assert prior_revision not in MIGRATION.name
    assert "ALTER TABLE" not in source.upper()


def test_m5_migration_locks_risk_evidence_and_annotation_invariants() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for invariant in (
        "risk_policy_version",
        "risk_reason_codes",
        "risk_score_detail",
        "evidence_status",
        "evidence_failure_code",
        "engine_version",
        "uk_review_item_evidence",
        "rank_no BETWEEN 1 AND 5",
        "RAG_SEARCH_UNAVAILABLE",
        "RAG_SEARCH_FAILED",
        "BOX",
        "TEXT_HIGHLIGHT",
        "LIST_ONLY",
        "UNAVAILABLE",
        "normalized_start_offset",
        "coordinate_confidence",
        "ck_annotations_box_coordinate",
        "ck_annotations_text_highlight",
    ):
        assert invariant in source
