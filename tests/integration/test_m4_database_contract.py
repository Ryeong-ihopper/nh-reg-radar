from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "apps"
    / "backend"
    / "migrations"
    / "versions"
    / "0004_m4_parser_ocr_jobs.py"
)


def test_m4_migration_is_additive_and_owns_parser_job_tables() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision: str | None = "0003_m3_standards_search"' in source
    for table in (
        "reviews",
        "review_jobs",
        "review_steps",
        "parser_artifacts",
        "ocr_text_blocks",
        "layout_blocks",
    ):
        assert f'"{table}"' in source
    for invariant in (
        "uk_reviews_active_advertisement",
        "fk_advertisements_latest_review",
        "fk_ad_revision_base_review",
        "uk_review_steps_job_code",
        "uk_parser_artifacts_object",
        "idx_review_jobs_status_retry",
        "idx_review_jobs_heartbeat",
        "idx_parser_artifacts_retention",
        "uk_parser_artifacts_selected_step",
        "confidence_policy_version",
        "normalized_start_offset",
        "coordinate_confidence",
        "is_selected_output",
        "dead_lettered_at",
    ):
        assert invariant in source
    assert "ALTER TABLE" not in source.upper()
