"""Create the M4 review job, normalized parser result, and artifact tables.

Revision ID: 0004_m4_parser_ocr_jobs
Revises: 0003_m3_standards_search
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_m4_parser_ocr_jobs"
down_revision: str | None = "0003_m3_standards_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_TABLES = (
    "reviews",
    "review_jobs",
    "review_steps",
    "parser_artifacts",
    "ocr_text_blocks",
    "layout_blocks",
)


def _coordinate_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("source_width", sa.Numeric(12, 4)),
        sa.Column("source_height", sa.Numeric(12, 4)),
        sa.Column("source_unit", sa.String(20)),
        sa.Column("coordinate_x", sa.Numeric(12, 4)),
        sa.Column("coordinate_y", sa.Numeric(12, 4)),
        sa.Column("coordinate_width", sa.Numeric(12, 4)),
        sa.Column("coordinate_height", sa.Numeric(12, 4)),
        sa.Column("normalized_x", sa.Numeric(8, 6)),
        sa.Column("normalized_y", sa.Numeric(8, 6)),
        sa.Column("normalized_width", sa.Numeric(8, 6)),
        sa.Column("normalized_height", sa.Numeric(8, 6)),
        sa.Column("rotation", sa.Numeric(8, 4)),
        sa.Column("coordinate_confidence", sa.Numeric(5, 4)),
    )


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("review_id", sa.String(50), primary_key=True),
        sa.Column(
            "advertisement_id",
            sa.String(50),
            sa.ForeignKey("app.advertisements.advertisement_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_revisions.revision_id", ondelete="SET NULL"),
        ),
        sa.Column("parent_review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id")),
        sa.Column("review_round", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(50), nullable=False),
        sa.Column("overall_risk_level", sa.String(50)),
        sa.Column("standard_effective_date", sa.Date(), nullable=False),
        sa.Column(
            "applied_standard_version_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("review_types", postgresql.JSONB(), nullable=False),
        sa.Column("include_suggestion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("include_opinion_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request_memo", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "requested_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("review_round >= 1", name="ck_reviews_round"),
        sa.CheckConstraint(
            "review_status IN ('ANALYSIS_REQUESTED','ANALYZING','CHECK_REQUIRED','REVIEW_COMPLETED','REVIEW_FAILED')",
            name="ck_reviews_status",
        ),
        schema="app",
    )
    op.create_index("idx_reviews_advertisement", "reviews", ["advertisement_id"], schema="app")
    op.create_index("idx_reviews_revision", "reviews", ["revision_id"], schema="app")
    op.create_index("idx_reviews_status", "reviews", ["review_status"], schema="app")
    op.create_index("idx_reviews_requested_at", "reviews", ["requested_at"], schema="app")
    op.create_index(
        "uk_reviews_active_advertisement",
        "reviews",
        ["advertisement_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("review_status IN ('ANALYSIS_REQUESTED','ANALYZING')"),
    )
    op.create_foreign_key(
        "fk_advertisements_latest_review",
        "advertisements",
        "reviews",
        ["latest_review_id"],
        ["review_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ad_revision_base_review",
        "advertisement_revisions",
        "reviews",
        ["base_review_id"],
        ["review_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="SET NULL",
    )

    op.create_table(
        "review_jobs",
        sa.Column("job_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("job_status", sa.String(50), nullable=False),
        sa.Column("queue_name", sa.String(100), nullable=False),
        sa.Column("progress_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(100)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("timeout_at", sa.DateTime(timezone=True)),
        sa.Column("enqueued_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.String(100)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_reason_code", sa.String(100)),
        sa.Column("failed_reason", sa.Text()),
        sa.Column("is_retryable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "job_status IN ('PENDING','RUNNING','RETRY_PENDING','STALE','COMPLETED','FAILED','FAILED_FINAL','CANCELED')",
            name="ck_review_jobs_status",
        ),
        sa.CheckConstraint("retry_count BETWEEN 0 AND max_retries", name="ck_review_jobs_retries"),
        sa.CheckConstraint("progress_rate BETWEEN 0 AND 100", name="ck_review_jobs_progress"),
        schema="app",
    )
    op.create_index(
        "idx_review_jobs_status_retry",
        "review_jobs",
        ["job_status", "next_retry_at"],
        schema="app",
    )
    op.create_index(
        "idx_review_jobs_heartbeat",
        "review_jobs",
        ["job_status", "heartbeat_at"],
        schema="app",
    )

    op.create_table(
        "review_steps",
        sa.Column("review_step_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(50),
            sa.ForeignKey("app.review_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_code", sa.String(100), nullable=False),
        sa.Column("step_name", sa.String(200), nullable=False),
        sa.Column("step_status", sa.String(50), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("timeout_at", sa.DateTime(timezone=True)),
        sa.Column("timeout_seconds", sa.Integer()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_reason_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("job_id", "step_code", name="uk_review_steps_job_code"),
        sa.CheckConstraint(
            "step_status IN ('PENDING','RUNNING','RETRY_PENDING','COMPLETED','FAILED','SKIPPED')",
            name="ck_review_steps_status",
        ),
        schema="app",
    )
    op.create_index("idx_review_steps_review", "review_steps", ["review_id"], schema="app")
    op.create_index("idx_review_steps_job", "review_steps", ["job_id"], schema="app")

    op.create_table(
        "parser_artifacts",
        sa.Column("raw_artifact_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id"), nullable=False
        ),
        sa.Column(
            "file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id"),
            nullable=False,
        ),
        sa.Column(
            "review_step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app.review_steps.review_step_id"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("storage_provider", sa.String(50), nullable=False),
        sa.Column("bucket", sa.String(100), nullable=False),
        sa.Column("object_key", sa.String(1000), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(200), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(100), nullable=False),
        sa.Column("parser_rule_version", sa.String(100), nullable=False),
        sa.Column("ir_version", sa.String(100), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("is_primary_attempt", sa.Boolean(), nullable=False),
        sa.Column("is_selected_output", sa.Boolean(), nullable=False),
        sa.Column("rerun_reason_code", sa.String(100)),
        sa.Column("rerun_reason_message", sa.Text()),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("confidence_status", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("bucket", "object_key", name="uk_parser_artifacts_object"),
        sa.CheckConstraint("attempt_no >= 1", name="ck_parser_artifacts_attempt"),
        sa.CheckConstraint("file_size >= 0", name="ck_parser_artifacts_size"),
        schema="app",
    )
    op.create_index("idx_parser_artifacts_review", "parser_artifacts", ["review_id"], schema="app")
    op.create_index("idx_parser_artifacts_file", "parser_artifacts", ["file_id"], schema="app")
    op.create_index(
        "idx_parser_artifacts_step", "parser_artifacts", ["review_step_id"], schema="app"
    )
    op.create_index(
        "idx_parser_artifacts_selected",
        "parser_artifacts",
        ["review_step_id", "is_selected_output"],
        schema="app",
    )
    op.create_index(
        "uk_parser_artifacts_selected_step",
        "parser_artifacts",
        ["review_step_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("is_selected_output"),
    )
    op.create_index(
        "idx_parser_artifacts_retention", "parser_artifacts", ["retention_until"], schema="app"
    )

    op.create_table(
        "ocr_text_blocks",
        sa.Column("ocr_block_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id"), nullable=False
        ),
        sa.Column(
            "file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id"),
            nullable=False,
        ),
        sa.Column("page_no", sa.Integer()),
        sa.Column("block_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_path", sa.String(500)),
        sa.Column("text_block_type", sa.String(50)),
        sa.Column("raw_start_offset", sa.Integer()),
        sa.Column("raw_end_offset", sa.Integer()),
        sa.Column("normalized_start_offset", sa.Integer()),
        sa.Column("normalized_end_offset", sa.Integer()),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(100), nullable=False),
        sa.Column("parser_rule_version", sa.String(100), nullable=False),
        sa.Column("ir_version", sa.String(100), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_status", sa.String(50), nullable=False),
        sa.Column("confidence_policy_version", sa.String(100), nullable=False),
        *_coordinate_columns(),
        sa.Column(
            "raw_artifact_id", sa.String(50), sa.ForeignKey("app.parser_artifacts.raw_artifact_id")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_ocr_blocks_confidence"),
        sa.CheckConstraint(
            "confidence_status IN ('READABLE','LOW_CONFIDENCE','UNREADABLE')",
            name="ck_ocr_blocks_confidence_status",
        ),
        sa.CheckConstraint(
            "((raw_start_offset IS NULL AND raw_end_offset IS NULL AND normalized_start_offset IS NULL AND normalized_end_offset IS NULL) OR "
            "(raw_start_offset >= 0 AND raw_end_offset >= raw_start_offset AND normalized_start_offset >= 0 AND normalized_end_offset >= normalized_start_offset))",
            name="ck_ocr_blocks_offset_pairs",
        ),
        schema="app",
    )
    op.create_index("idx_ocr_blocks_review", "ocr_text_blocks", ["review_id"], schema="app")
    op.create_index(
        "idx_ocr_blocks_file_page", "ocr_text_blocks", ["file_id", "page_no"], schema="app"
    )
    op.create_index(
        "idx_ocr_blocks_text_path", "ocr_text_blocks", ["file_id", "text_path"], schema="app"
    )

    op.create_table(
        "layout_blocks",
        sa.Column("layout_block_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id", sa.String(50), sa.ForeignKey("app.reviews.review_id"), nullable=False
        ),
        sa.Column(
            "file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id"),
            nullable=False,
        ),
        sa.Column("page_no", sa.Integer()),
        sa.Column("layout_type", sa.String(50), nullable=False),
        *_coordinate_columns(),
        sa.Column(
            "related_ocr_block_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "raw_artifact_id", sa.String(50), sa.ForeignKey("app.parser_artifacts.raw_artifact_id")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_layout_blocks_confidence"),
        schema="app",
    )
    op.create_index("idx_layout_blocks_review", "layout_blocks", ["review_id"], schema="app")
    op.create_index(
        "idx_layout_blocks_file_page", "layout_blocks", ["file_id", "page_no"], schema="app"
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA app TO readonly")


def downgrade() -> None:
    op.drop_constraint(
        "fk_ad_revision_base_review", "advertisement_revisions", schema="app", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_advertisements_latest_review", "advertisements", schema="app", type_="foreignkey"
    )
    for table_name in reversed(APP_TABLES):
        op.drop_table(table_name, schema="app")
