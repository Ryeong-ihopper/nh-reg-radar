"""Create the M6 immutable support-output and comparison tables.

Revision ID: 0006_m6_support_outputs
Revises: 0005_m5_review_results
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_m6_support_outputs"
down_revision: str | None = "0005_m5_review_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suggestions",
        sa.Column("suggestion_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_item_id",
            sa.String(50),
            sa.ForeignKey("app.review_items.review_item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("suggested_text", sa.Text(), nullable=False),
        sa.Column("suggestion_reason", sa.Text()),
        sa.Column("suggestion_type", sa.String(50), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB()),
        sa.Column("decision_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "suggestion_type IN ('ALTERNATIVE','ADDITIONAL_NOTICE','SOFTENING')",
            name="ck_suggestions_type",
        ),
        sa.CheckConstraint(
            "decision_status IN ('PENDING','ACCEPTED','REJECTED','MODIFIED_AND_USED')",
            name="ck_suggestions_decision",
        ),
        schema="app",
    )
    op.create_index("idx_suggestions_review", "suggestions", ["review_id"], schema="app")
    op.create_index("idx_suggestions_item", "suggestions", ["review_item_id"], schema="app")
    op.create_index("idx_suggestions_decision", "suggestions", ["decision_status"], schema="app")
    op.create_table(
        "suggestion_decisions",
        sa.Column("suggestion_decision_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.String(50),
            sa.ForeignKey("app.suggestions.suggestion_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_status", sa.String(50), nullable=False),
        sa.Column("final_text", sa.Text()),
        sa.Column("comment", sa.Text()),
        sa.Column("decided_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision_status IN ('ACCEPTED','REJECTED','MODIFIED_AND_USED')",
            name="ck_suggestion_decisions_status",
        ),
        sa.CheckConstraint(
            "(decision_status <> 'MODIFIED_AND_USED') OR final_text IS NOT NULL",
            name="ck_suggestion_decisions_final_text",
        ),
        schema="app",
    )
    op.create_index(
        "idx_suggestion_decisions_history",
        "suggestion_decisions",
        ["suggestion_id", "decided_at"],
        schema="app",
    )

    op.create_table(
        "qa_sessions",
        sa.Column("qa_session_id", sa.String(50), primary_key=True),
        sa.Column("user_id", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.Column("product_group", sa.String(50)),
        sa.Column("advertisement_type", sa.String(50)),
        sa.Column("standard_effective_date", sa.Date()),
        sa.Column("standard_version_ids", postgresql.JSONB(), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="rag",
    )
    op.create_table(
        "qa_messages",
        sa.Column("qa_message_id", sa.String(50), primary_key=True),
        sa.Column(
            "qa_session_id",
            sa.String(50),
            sa.ForeignKey("rag.qa_sessions.qa_session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_summary", sa.Text()),
        sa.Column("answer_detail", sa.Text()),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False),
        sa.Column("suggested_phrases", postgresql.JSONB()),
        sa.Column("raw_response_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="rag",
    )
    op.create_table(
        "qa_message_evidences",
        sa.Column("qa_message_evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "qa_message_id",
            sa.String(50),
            sa.ForeignKey("rag.qa_messages.qa_message_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id", sa.String(50), sa.ForeignKey("rag.evidences.evidence_id"), nullable=False
        ),
        sa.Column(
            "standard_version_id",
            sa.String(50),
            sa.ForeignKey("rag.standard_versions.standard_version_id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_chunk_id",
            sa.String(50),
            sa.ForeignKey("rag.evidence_chunks.evidence_chunk_id"),
        ),
        sa.Column("relevance_score", sa.Numeric(5, 4)),
        sa.Column("rank_no", sa.Integer()),
        sa.CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1",
            name="ck_qa_evidence_score",
        ),
        sa.CheckConstraint(
            "rank_no IS NULL OR rank_no BETWEEN 1 AND 5", name="ck_qa_evidence_rank"
        ),
        schema="rag",
    )
    op.create_index(
        "idx_qa_messages_session", "qa_messages", ["qa_session_id", "created_at"], schema="rag"
    )

    op.create_table(
        "opinion_drafts",
        sa.Column("draft_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_type", sa.String(100), nullable=False),
        sa.Column("draft_content", sa.Text(), nullable=False),
        sa.Column("final_content", sa.Text()),
        sa.Column("included_review_item_ids", postgresql.JSONB()),
        sa.Column("additional_instruction", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100), sa.ForeignKey("app.users.user_id")),
        schema="app",
    )
    op.create_table(
        "reports",
        sa.Column("report_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_report_id", sa.String(50), sa.ForeignKey("app.reports.report_id")),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("report_format", sa.String(30), nullable=False),
        sa.Column("report_status", sa.String(50), nullable=False),
        sa.Column("file_id", sa.String(50), sa.ForeignKey("app.advertisement_files.file_id")),
        sa.Column("report_payload", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_hash", sa.String(128), nullable=False),
        sa.Column("snapshot_version", sa.String(50), nullable=False),
        sa.Column("renderer_version", sa.String(100)),
        sa.Column("converter_version", sa.String(100)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("include_annotations", sa.Boolean(), nullable=False),
        sa.Column("include_suggestions", sa.Boolean(), nullable=False),
        sa.Column("include_opinion_draft", sa.Boolean(), nullable=False),
        sa.Column("include_evidence_details", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.CheckConstraint("report_type IN ('FULL','SELECTED')", name="ck_reports_type"),
        sa.CheckConstraint("report_format IN ('HWPX','PDF')", name="ck_reports_format"),
        sa.CheckConstraint("report_status IN ('CREATED','FAILED')", name="ck_reports_status"),
        sa.CheckConstraint(
            "report_format <> 'PDF' OR source_report_id IS NOT NULL", name="ck_reports_pdf_source"
        ),
        schema="app",
    )
    for name, columns in (
        ("idx_reports_review", ["review_id"]),
        ("idx_reports_source", ["source_report_id"]),
        ("idx_reports_snapshot_hash", ["snapshot_hash"]),
    ):
        op.create_index(name, "reports", columns, schema="app")

    op.create_table(
        "comparisons",
        sa.Column("comparison_id", sa.String(50), primary_key=True),
        sa.Column(
            "advertisement_id",
            sa.String(50),
            sa.ForeignKey("app.advertisements.advertisement_id"),
            nullable=False,
        ),
        sa.Column(
            "base_review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id"), nullable=False
        ),
        sa.Column(
            "revision_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_revisions.revision_id"),
            nullable=False,
        ),
        sa.Column("reanalysis_review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id")),
        sa.Column("comparison_status", sa.String(50), nullable=False),
        sa.Column("compare_types", postgresql.JSONB(), nullable=False),
        sa.Column("resolved_issue_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_issue_count", sa.Integer(), nullable=False),
        sa.Column("new_issue_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.CheckConstraint(
            "comparison_status IN ('COMPLETED','FAILED')", name="ck_comparisons_status"
        ),
        schema="app",
    )
    op.create_table(
        "comparison_items",
        sa.Column("comparison_item_id", sa.String(50), primary_key=True),
        sa.Column(
            "comparison_id",
            sa.String(50),
            sa.ForeignKey("app.comparisons.comparison_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_item_id", sa.String(50), sa.ForeignKey("app.review_items.review_item_id")
        ),
        sa.Column("original_text", sa.Text()),
        sa.Column("revised_text", sa.Text()),
        sa.Column("resolution_status", sa.String(50), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("reanalysis_review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "resolution_status IN ('RESOLVED','UNRESOLVED','NEW_ISSUE','CHECK_REQUIRED')",
            name="ck_comparison_items_resolution",
        ),
        schema="app",
    )
    op.create_index(
        "idx_comparisons_advertisement",
        "comparisons",
        ["advertisement_id", "created_at"],
        schema="app",
    )
    op.create_index(
        "idx_comparison_items_comparison", "comparison_items", ["comparison_id"], schema="app"
    )


def downgrade() -> None:
    for table, schema in (
        ("comparison_items", "app"),
        ("comparisons", "app"),
        ("reports", "app"),
        ("opinion_drafts", "app"),
        ("qa_message_evidences", "rag"),
        ("qa_messages", "rag"),
        ("qa_sessions", "rag"),
        ("suggestion_decisions", "app"),
        ("suggestions", "app"),
    ):
        op.drop_table(table, schema=schema)
