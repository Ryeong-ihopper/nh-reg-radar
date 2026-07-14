"""Create the M5 review result, evidence mapping, and annotation tables.

Revision ID: 0005_m5_review_results
Revises: 0004_m4_parser_ocr_jobs
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_m5_review_results"
down_revision: str | None = "0004_m4_parser_ocr_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_TABLES = (
    "review_items",
    "review_item_evidences",
    "annotations",
)


def _annotation_coordinate_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("source_width", sa.Numeric(12, 4)),
        sa.Column("source_height", sa.Numeric(12, 4)),
        sa.Column("source_unit", sa.String(20)),
        sa.Column("x", sa.Numeric(12, 4)),
        sa.Column("y", sa.Numeric(12, 4)),
        sa.Column("width", sa.Numeric(12, 4)),
        sa.Column("height", sa.Numeric(12, 4)),
        sa.Column("normalized_x", sa.Numeric(8, 7)),
        sa.Column("normalized_y", sa.Numeric(8, 7)),
        sa.Column("normalized_width", sa.Numeric(8, 7)),
        sa.Column("normalized_height", sa.Numeric(8, 7)),
        sa.Column("rotation", sa.Numeric(6, 2)),
        sa.Column("coordinate_confidence", sa.Numeric(5, 4)),
    )


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("review_item_id", sa.String(50), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("review_type", sa.String(50), nullable=False),
        sa.Column("target_text", sa.Text()),
        sa.Column("normalized_target_text", sa.Text()),
        sa.Column(
            "ocr_block_id",
            sa.String(50),
            sa.ForeignKey("app.ocr_text_blocks.ocr_block_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "layout_block_id",
            sa.String(50),
            sa.ForeignKey("app.layout_blocks.layout_block_id", ondelete="SET NULL"),
        ),
        sa.Column("result_status", sa.String(50), nullable=False),
        sa.Column("risk_level", sa.String(50), nullable=False),
        sa.Column("risk_policy_version", sa.String(100), nullable=False),
        sa.Column("risk_reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("risk_score_detail", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_status", sa.String(50), nullable=False),
        sa.Column("evidence_failure_code", sa.String(100)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text()),
        sa.Column("engine_type", sa.String(50), nullable=False),
        sa.Column("engine_version", sa.String(100), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("page_no", sa.Integer()),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "result_status IN ('APPROPRIATE','NEEDS_REVISION','NEEDS_CONFIRMATION')",
            name="ck_review_items_result_status",
        ),
        sa.CheckConstraint(
            "risk_level IN ('HIGH','MEDIUM','LOW','CHECK_REQUIRED')",
            name="ck_review_items_risk_level",
        ),
        sa.CheckConstraint(
            "engine_type IN ('RULE','RAG','MULTIMODAL','LLM')",
            name="ck_review_items_engine_type",
        ),
        sa.CheckConstraint(
            "evidence_status IN ('CONNECTED','NOT_REQUIRED','INSUFFICIENT','SEARCH_UNAVAILABLE')",
            name="ck_review_items_evidence_status",
        ),
        sa.CheckConstraint(
            "((evidence_status = 'SEARCH_UNAVAILABLE' AND evidence_failure_code IN ('RAG_SEARCH_UNAVAILABLE','RAG_SEARCH_FAILED')) OR "
            "(evidence_status <> 'SEARCH_UNAVAILABLE' AND evidence_failure_code IS NULL))",
            name="ck_review_items_evidence_failure",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1",
            name="ck_review_items_confidence",
        ),
        schema="app",
    )
    op.create_index("idx_review_items_review", "review_items", ["review_id"], schema="app")
    op.create_index("idx_review_items_type", "review_items", ["review_type"], schema="app")
    op.create_index("idx_review_items_status", "review_items", ["result_status"], schema="app")
    op.create_index("idx_review_items_risk", "review_items", ["risk_level"], schema="app")
    op.create_index("idx_review_items_ocr_block", "review_items", ["ocr_block_id"], schema="app")
    op.create_index(
        "idx_review_items_evidence_status",
        "review_items",
        ["evidence_status"],
        schema="app",
    )

    op.create_table(
        "review_item_evidences",
        sa.Column("review_item_evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_item_id",
            sa.String(50),
            sa.ForeignKey("app.review_items.review_item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(50),
            sa.ForeignKey("rag.evidences.evidence_id"),
            nullable=False,
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
        sa.Column("matched_text", sa.Text()),
        sa.Column("relevance_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("rank_no", sa.Integer(), nullable=False),
        sa.Column("match_source", sa.String(50), nullable=False),
        sa.Column("score_detail", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "review_item_id",
            "evidence_id",
            "evidence_chunk_id",
            name="uk_review_item_evidence",
        ),
        sa.CheckConstraint("relevance_score BETWEEN 0 AND 1", name="ck_item_evidence_score"),
        sa.CheckConstraint("rank_no BETWEEN 1 AND 5", name="ck_item_evidence_rank"),
        sa.CheckConstraint(
            "match_source IN ('KEYWORD','VECTOR','HYBRID','RULE_METADATA')",
            name="ck_item_evidence_source",
        ),
        schema="app",
    )
    op.create_index(
        "idx_review_item_evidences_item_rank",
        "review_item_evidences",
        ["review_item_id", "rank_no"],
        schema="app",
    )
    op.create_index(
        "idx_review_item_evidences_chunk",
        "review_item_evidences",
        ["evidence_chunk_id"],
        schema="app",
    )

    op.create_table(
        "annotations",
        sa.Column("annotation_id", sa.String(50), primary_key=True),
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
        sa.Column(
            "file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id"),
            nullable=False,
        ),
        sa.Column("page_no", sa.Integer()),
        sa.Column(
            "text_block_id",
            sa.String(50),
            sa.ForeignKey("app.ocr_text_blocks.ocr_block_id", ondelete="SET NULL"),
        ),
        sa.Column("text_path", sa.String(500)),
        sa.Column("annotation_display_mode", sa.String(50), nullable=False),
        sa.Column("annotation_status", sa.String(50), nullable=False),
        sa.Column("location_confidence", sa.Numeric(5, 4)),
        sa.Column("confidence_policy_version", sa.String(100), nullable=False),
        sa.Column("display_reason", sa.String(100), nullable=False),
        sa.Column("annotation_type", sa.String(50)),
        *_annotation_coordinate_columns(),
        sa.Column("raw_start_offset", sa.Integer()),
        sa.Column("raw_end_offset", sa.Integer()),
        sa.Column("normalized_start_offset", sa.Integer()),
        sa.Column("normalized_end_offset", sa.Integer()),
        sa.Column("matched_text", sa.Text()),
        sa.Column("risk_level", sa.String(50), nullable=False),
        sa.Column("review_type", sa.String(50), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "annotation_display_mode IN ('BOX','TEXT_HIGHLIGHT','LIST_ONLY','UNAVAILABLE')",
            name="ck_annotations_display_mode",
        ),
        sa.CheckConstraint(
            "annotation_status IN ('LOCATED','PARTIALLY_LOCATED','NOT_LOCATED','LOW_CONFIDENCE','DOCUMENT_LEVEL_ISSUE')",
            name="ck_annotations_status",
        ),
        sa.CheckConstraint(
            "risk_level IN ('HIGH','MEDIUM','LOW','CHECK_REQUIRED')",
            name="ck_annotations_risk_level",
        ),
        sa.CheckConstraint(
            "location_confidence IS NULL OR location_confidence BETWEEN 0 AND 1",
            name="ck_annotations_location_confidence",
        ),
        sa.CheckConstraint(
            "coordinate_confidence IS NULL OR coordinate_confidence BETWEEN 0 AND 1",
            name="ck_annotations_coordinate_confidence",
        ),
        sa.CheckConstraint(
            "normalized_x IS NULL OR (normalized_x BETWEEN 0 AND 1 AND normalized_y BETWEEN 0 AND 1 "
            "AND normalized_width BETWEEN 0 AND 1 AND normalized_height BETWEEN 0 AND 1)",
            name="ck_annotations_normalized_coordinate",
        ),
        sa.CheckConstraint(
            "((annotation_display_mode = 'BOX' AND source_width IS NOT NULL AND source_height IS NOT NULL "
            "AND source_unit IS NOT NULL AND x IS NOT NULL AND y IS NOT NULL AND width IS NOT NULL "
            "AND height IS NOT NULL AND normalized_x IS NOT NULL AND normalized_y IS NOT NULL "
            "AND normalized_width IS NOT NULL AND normalized_height IS NOT NULL) OR "
            "(annotation_display_mode <> 'BOX'))",
            name="ck_annotations_box_coordinate",
        ),
        sa.CheckConstraint(
            "((annotation_display_mode = 'TEXT_HIGHLIGHT' AND text_block_id IS NOT NULL "
            "AND normalized_start_offset >= 0 AND normalized_end_offset >= normalized_start_offset) OR "
            "(annotation_display_mode <> 'TEXT_HIGHLIGHT'))",
            name="ck_annotations_text_highlight",
        ),
        schema="app",
    )
    op.create_index("idx_annotations_review", "annotations", ["review_id"], schema="app")
    op.create_index(
        "idx_annotations_file_page", "annotations", ["file_id", "page_no"], schema="app"
    )
    op.create_index("idx_annotations_item", "annotations", ["review_item_id"], schema="app")
    op.create_index(
        "idx_annotations_type_risk",
        "annotations",
        ["review_type", "risk_level"],
        schema="app",
    )
    op.create_index(
        "idx_annotations_display_status",
        "annotations",
        ["annotation_display_mode", "annotation_status"],
        schema="app",
    )
    op.create_index("idx_annotations_text_block", "annotations", ["text_block_id"], schema="app")

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA app TO readonly")


def downgrade() -> None:
    for table_name in reversed(APP_TABLES):
        op.drop_table(table_name, schema="app")
