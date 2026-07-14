"""Create the M7 validation dataset and immutable KPI snapshot tables.

Revision ID: 0007_m7_validation_kpi
Revises: 0006_m6_support_outputs
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_m7_validation_kpi"
down_revision: str | None = "0006_m6_support_outputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXCLUDE_REASON_CHECK = (
    "exclude_reason_code IS NULL OR exclude_reason_code IN "
    "('OCR_UNREADABLE','PRODUCT_CONDITION_AMBIGUOUS','REFERENCE_NOT_PROVIDED',"
    "'SOURCE_FILE_CORRUPTED','LABEL_UNCLEAR','DUPLICATE_SAMPLE','OUT_OF_SCOPE')"
)


def upgrade() -> None:
    op.create_table(
        "validation_datasets",
        sa.Column("dataset_id", sa.String(50), primary_key=True),
        sa.Column("dataset_name", sa.String(300), nullable=False),
        sa.Column(
            "advertisement_id",
            sa.String(50),
            sa.ForeignKey("app.advertisements.advertisement_id", ondelete="SET NULL"),
        ),
        sa.Column("product_group", sa.String(50), nullable=False),
        sa.Column("advertisement_type", sa.String(50), nullable=False),
        sa.Column(
            "sample_file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "product_condition_file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id", ondelete="SET NULL"),
        ),
        sa.Column("human_review_comment", sa.Text()),
        sa.Column("label_json", postgresql.JSONB()),
        sa.Column("dataset_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exclude_reason_code", sa.String(100)),
        sa.Column("exclude_reason", sa.Text()),
        sa.Column("excluded_by", sa.String(100), sa.ForeignKey("app.users.user_id")),
        sa.Column("excluded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100), sa.ForeignKey("app.users.user_id")),
        sa.CheckConstraint("dataset_version > 0", name="ck_validation_datasets_version"),
        sa.CheckConstraint(EXCLUDE_REASON_CHECK, name="ck_validation_datasets_exclude_reason"),
        sa.CheckConstraint(
            "NOT is_excluded OR (exclude_reason_code IS NOT NULL AND excluded_by IS NOT NULL "
            "AND excluded_at IS NOT NULL)",
            name="ck_validation_datasets_exclusion_approval",
        ),
        schema="validation",
    )
    for name, columns in (
        ("idx_validation_datasets_classification", ["product_group", "advertisement_type"]),
        ("idx_validation_datasets_version", ["dataset_version"]),
        ("idx_validation_datasets_created", ["created_at"]),
    ):
        op.create_index(name, "validation_datasets", columns, schema="validation")

    op.create_table(
        "validation_judgments",
        sa.Column("judgment_id", sa.String(50), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(50),
            sa.ForeignKey("validation.validation_datasets.dataset_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("review_type", sa.String(50), nullable=False),
        sa.Column("expected_status", sa.String(50), nullable=False),
        sa.Column("risk_level", sa.String(50)),
        sa.Column("evidence_comment", sa.Text()),
        sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exclude_reason_code", sa.String(100)),
        sa.Column("exclude_reason", sa.Text()),
        sa.Column("excluded_by", sa.String(100), sa.ForeignKey("app.users.user_id")),
        sa.Column("excluded_at", sa.DateTime(timezone=True)),
        sa.Column("judgment_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("judged_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.Column(
            "judged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100), sa.ForeignKey("app.users.user_id")),
        sa.CheckConstraint("judgment_version > 0", name="ck_validation_judgments_version"),
        sa.CheckConstraint(
            "review_type IN ('REQUIRED_PHRASE','INTEREST_RATE','MISLEADING_EXPRESSION',"
            "'PRODUCT_CONSISTENCY','VISIBILITY','OCR_QUALITY')",
            name="ck_validation_judgments_review_type",
        ),
        sa.CheckConstraint(
            "expected_status IN ('APPROPRIATE','NEEDS_REVISION','NEEDS_CONFIRMATION')",
            name="ck_validation_judgments_expected_status",
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('HIGH','MEDIUM','LOW','CHECK_REQUIRED')",
            name="ck_validation_judgments_risk_level",
        ),
        sa.CheckConstraint(EXCLUDE_REASON_CHECK, name="ck_validation_judgments_exclude_reason"),
        sa.CheckConstraint(
            "NOT is_excluded OR (exclude_reason_code IS NOT NULL AND excluded_by IS NOT NULL "
            "AND excluded_at IS NOT NULL)",
            name="ck_validation_judgments_exclusion_approval",
        ),
        schema="validation",
    )
    op.create_index(
        "idx_validation_judgments_dataset",
        "validation_judgments",
        ["dataset_id", "review_type", "judgment_version"],
        schema="validation",
    )

    op.create_table(
        "evaluations",
        sa.Column("evaluation_id", sa.String(50), primary_key=True),
        sa.Column("evaluation_name", sa.String(300)),
        sa.Column("evaluation_status", sa.String(50), nullable=False),
        sa.Column("dataset_ids", postgresql.JSONB(), nullable=False),
        sa.Column("exclude_invalid_samples", sa.Boolean(), nullable=False),
        sa.Column("review_selection_policy", sa.String(50), nullable=False),
        sa.Column("total_sample_count", sa.Integer(), nullable=False),
        sa.Column("excluded_sample_count", sa.Integer(), nullable=False),
        sa.Column("exclusion_summary_json", postgresql.JSONB()),
        sa.Column("dataset_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("judgment_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("exclusion_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("ai_result_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("version_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("evaluation_policy_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_hash", sa.String(128), nullable=False),
        sa.Column("snapshot_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(100), sa.ForeignKey("app.users.user_id"), nullable=False),
        sa.CheckConstraint(
            "evaluation_status IN ('COMPLETED','FAILED')",
            name="ck_evaluations_status",
        ),
        sa.CheckConstraint(
            "review_selection_policy IN ('LATEST_COMPLETED')",
            name="ck_evaluations_review_selection_policy",
        ),
        sa.CheckConstraint(
            "total_sample_count >= 0 AND excluded_sample_count >= 0 "
            "AND excluded_sample_count <= total_sample_count",
            name="ck_evaluations_sample_counts",
        ),
        sa.CheckConstraint(
            "snapshot_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_evaluations_snapshot_hash",
        ),
        schema="validation",
    )
    op.create_index("idx_evaluations_created", "evaluations", ["created_at"], schema="validation")
    op.create_index(
        "idx_evaluations_snapshot_hash", "evaluations", ["snapshot_hash"], schema="validation"
    )

    op.create_table(
        "evaluation_metrics",
        sa.Column("evaluation_metric_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.String(50),
            sa.ForeignKey("validation.evaluations.evaluation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_code", sa.String(100), nullable=False),
        sa.Column("metric_name", sa.String(200), nullable=False),
        sa.Column("score", sa.Numeric(6, 2)),
        sa.Column("target_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("achieved", sa.Boolean(), nullable=False),
        sa.Column("numerator", sa.Numeric(10, 2), nullable=False),
        sa.Column("denominator", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("not_applicable", sa.Boolean(), nullable=False),
        sa.Column("detail_json", postgresql.JSONB()),
        sa.CheckConstraint(
            "metric_code IN ('REQUIRED_PHRASE_ACCURACY','MISLEADING_EXPRESSION_ACCURACY',"
            "'EVIDENCE_PRECISION','HUMAN_AGREEMENT_RATE')",
            name="ck_evaluation_metrics_code",
        ),
        sa.CheckConstraint(
            "target_score >= 0 AND target_score <= 100",
            name="ck_evaluation_metrics_target",
        ),
        sa.CheckConstraint(
            "numerator >= 0 AND denominator >= 0 AND excluded_count >= 0 AND partial_count >= 0",
            name="ck_evaluation_metrics_counts",
        ),
        sa.CheckConstraint(
            "(not_applicable AND denominator = 0 AND score IS NULL AND NOT achieved) OR "
            "(NOT not_applicable AND denominator > 0 AND score BETWEEN 0 AND 100)",
            name="ck_evaluation_metrics_not_applicable",
        ),
        sa.UniqueConstraint("evaluation_id", "metric_code", name="uk_evaluation_metric_code"),
        schema="validation",
    )
    op.create_index(
        "idx_evaluation_metrics_evaluation",
        "evaluation_metrics",
        ["evaluation_id"],
        schema="validation",
    )

    op.execute("GRANT USAGE ON SCHEMA validation TO app, readonly")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA validation TO app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA validation TO readonly")


def downgrade() -> None:
    for table in (
        "evaluation_metrics",
        "evaluations",
        "validation_judgments",
        "validation_datasets",
    ):
        op.drop_table(table, schema="validation")
