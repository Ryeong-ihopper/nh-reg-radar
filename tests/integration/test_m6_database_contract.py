from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2] / "apps/backend/migrations/versions/0006_m6_support_outputs.py"
)


def test_m6_migration_is_additive_and_owned_by_m6() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0005_m5_review_results"' in source
    for table in (
        "suggestions",
        "suggestion_decisions",
        "qa_sessions",
        "qa_messages",
        "qa_message_evidences",
        "opinion_drafts",
        "reports",
        "comparisons",
        "comparison_items",
    ):
        assert f'"{table}"' in source
    assert "ALTER TABLE" not in source.upper()


def test_m6_migration_locks_history_snapshot_and_comparison_invariants() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for invariant in (
        "ck_suggestion_decisions_final_text",
        "MODIFIED_AND_USED",
        "standard_version_ids",
        "needs_human_review",
        "draft_content",
        "final_content",
        "report_payload",
        "snapshot_hash",
        "source_report_id",
        "ck_reports_pdf_source",
        "reanalysis_review_id",
        "RESOLVED",
        "UNRESOLVED",
        "NEW_ISSUE",
    ):
        assert invariant in source
