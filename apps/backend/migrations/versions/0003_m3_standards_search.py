"""Create the M3 standards, immutable versions, evidence, and reindex tables.

Revision ID: 0003_m3_standards_search
Revises: 0002_m2_auth_advertisement_audit
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_m3_standards_search"
down_revision: str | None = "0002_m2_auth_advertisement_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAG_TABLES = (
    "standards",
    "standard_versions",
    "evidences",
    "evidence_chunks",
    "standard_reindex_jobs",
)

INDEX_STATUSES = "('PENDING', 'INDEXING', 'ACTIVE', 'FAILED', 'EXCLUDED', 'DELETED')"


def upgrade() -> None:
    op.create_table(
        "standards",
        sa.Column("standard_id", sa.String(50), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("evidence_type", sa.String(50), nullable=False),
        sa.Column("product_group", sa.String(50)),
        sa.Column("advertisement_type", sa.String(50)),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("importance", sa.String(50)),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expired_date", sa.Date()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("current_version", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_by",
            sa.String(100),
            sa.ForeignKey("app.users.user_id"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100), sa.ForeignKey("app.users.user_id")),
        sa.CheckConstraint(
            "expired_date IS NULL OR effective_date IS NULL OR expired_date >= effective_date",
            name="ck_standards_effective_window",
        ),
        schema="rag",
    )
    op.create_index("idx_standards_type", "standards", ["evidence_type"], schema="rag")
    op.create_index(
        "idx_standards_product_ad_type",
        "standards",
        ["product_group", "advertisement_type"],
        schema="rag",
    )
    op.create_index("idx_standards_rule_type", "standards", ["rule_type"], schema="rag")
    op.create_index("idx_standards_effective_date", "standards", ["effective_date"], schema="rag")
    op.create_index("idx_standards_active", "standards", ["is_active"], schema="rag")

    op.create_table(
        "standard_versions",
        sa.Column("standard_version_id", sa.String(50), primary_key=True),
        sa.Column(
            "standard_id",
            sa.String(50),
            sa.ForeignKey("rag.standards.standard_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source_file_id",
            sa.String(50),
            sa.ForeignKey("app.advertisement_files.file_id", ondelete="SET NULL"),
        ),
        sa.Column("change_reason", sa.Text()),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expired_date", sa.Date()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_by",
            sa.String(100),
            sa.ForeignKey("app.users.user_id"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expired_date IS NULL OR effective_date IS NULL OR expired_date >= effective_date",
            name="ck_standard_versions_effective_window",
        ),
        sa.UniqueConstraint("standard_id", "version", name="uk_standard_versions"),
        schema="rag",
    )
    op.create_index(
        "idx_standard_versions_effective",
        "standard_versions",
        ["standard_id", "effective_date", "expired_date"],
        schema="rag",
    )

    op.create_table(
        "evidences",
        sa.Column("evidence_id", sa.String(50), primary_key=True),
        sa.Column(
            "standard_id",
            sa.String(50),
            sa.ForeignKey("rag.standards.standard_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "standard_version_id",
            sa.String(50),
            sa.ForeignKey("rag.standard_versions.standard_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("article_no", sa.String(100)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_summary", sa.Text()),
        sa.Column("product_group", sa.String(50)),
        sa.Column("advertisement_type", sa.String(50)),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("importance", sa.String(50)),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expired_date", sa.Date()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "standard_id", "standard_version_id", name="uk_evidences_standard_version"
        ),
        schema="rag",
    )
    op.create_index("idx_evidences_standard", "evidences", ["standard_id"], schema="rag")
    op.create_index("idx_evidences_type", "evidences", ["evidence_type"], schema="rag")
    op.create_index("idx_evidences_rule", "evidences", ["rule_type"], schema="rag")
    op.create_index(
        "idx_evidences_product_ad_type",
        "evidences",
        ["product_group", "advertisement_type"],
        schema="rag",
    )
    op.create_index("idx_evidences_article_no", "evidences", ["article_no"], schema="rag")
    op.create_index(
        "idx_evidences_effective_active",
        "evidences",
        ["effective_date", "expired_date", "is_active"],
        schema="rag",
    )

    op.create_table(
        "evidence_chunks",
        sa.Column("evidence_chunk_id", sa.String(50), primary_key=True),
        sa.Column(
            "evidence_id",
            sa.String(50),
            sa.ForeignKey("rag.evidences.evidence_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "standard_id",
            sa.String(50),
            sa.ForeignKey("rag.standards.standard_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "standard_version_id",
            sa.String(50),
            sa.ForeignKey("rag.standard_versions.standard_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_no", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer()),
        sa.Column("section_path", sa.String(500)),
        sa.Column("article_no", sa.String(100)),
        sa.Column("page_no", sa.Integer()),
        sa.Column("source_span", postgresql.JSONB()),
        sa.Column("structure_confidence", sa.Numeric(5, 4)),
        sa.Column("parser_rule_version", sa.String(100)),
        sa.Column("chunking_policy_version", sa.String(100), nullable=False),
        sa.Column("qdrant_collection", sa.String(100)),
        sa.Column("qdrant_point_id", sa.String(255)),
        sa.Column("qdrant_index_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("qdrant_indexed_at", sa.DateTime(timezone=True)),
        sa.Column("qdrant_index_error_code", sa.String(100)),
        sa.Column("qdrant_index_error_message", sa.Text()),
        sa.Column("opensearch_index", sa.String(100)),
        sa.Column("opensearch_doc_id", sa.String(255)),
        sa.Column(
            "opensearch_index_status", sa.String(50), nullable=False, server_default="PENDING"
        ),
        sa.Column("opensearch_indexed_at", sa.DateTime(timezone=True)),
        sa.Column("opensearch_index_error_code", sa.String(100)),
        sa.Column("opensearch_index_error_message", sa.Text()),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("search_schema_version", sa.String(100), nullable=False),
        sa.Column("opensearch_analyzer_version", sa.String(100)),
        sa.Column("synonym_version", sa.String(100)),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("chunk_no > 0", name="ck_evidence_chunks_chunk_no"),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0", name="ck_evidence_chunks_token_count"
        ),
        sa.CheckConstraint(
            "structure_confidence IS NULL OR "
            "(structure_confidence >= 0 AND structure_confidence <= 1)",
            name="ck_evidence_chunks_structure_confidence",
        ),
        sa.CheckConstraint(
            f"qdrant_index_status IN {INDEX_STATUSES}",
            name="ck_evidence_chunks_qdrant_status",
        ),
        sa.CheckConstraint(
            f"opensearch_index_status IN {INDEX_STATUSES}",
            name="ck_evidence_chunks_opensearch_status",
        ),
        sa.UniqueConstraint(
            "standard_version_id", "chunk_no", name="uk_evidence_chunks_version_no"
        ),
        sa.UniqueConstraint(
            "qdrant_collection", "qdrant_point_id", name="uk_evidence_chunks_qdrant_id"
        ),
        sa.UniqueConstraint(
            "opensearch_index", "opensearch_doc_id", name="uk_evidence_chunks_opensearch_id"
        ),
        schema="rag",
    )
    op.create_index(
        "idx_evidence_chunks_evidence", "evidence_chunks", ["evidence_id"], schema="rag"
    )
    op.create_index(
        "idx_evidence_chunks_standard_version",
        "evidence_chunks",
        ["standard_version_id"],
        schema="rag",
    )
    op.create_index(
        "idx_evidence_chunks_qdrant",
        "evidence_chunks",
        ["qdrant_collection", "qdrant_point_id"],
        schema="rag",
    )
    op.create_index(
        "idx_evidence_chunks_opensearch",
        "evidence_chunks",
        ["opensearch_index", "opensearch_doc_id"],
        schema="rag",
    )
    op.create_index(
        "idx_evidence_chunks_index_status",
        "evidence_chunks",
        ["qdrant_index_status", "opensearch_index_status"],
        schema="rag",
    )

    op.create_table(
        "standard_reindex_jobs",
        sa.Column("reindex_job_id", sa.String(50), primary_key=True),
        sa.Column(
            "standard_id",
            sa.String(50),
            sa.ForeignKey("rag.standards.standard_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "standard_version_id",
            sa.String(50),
            sa.ForeignKey("rag.standard_versions.standard_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reindex_scope", sa.String(50), nullable=False),
        sa.Column("job_status", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("target_indexes", postgresql.JSONB(), nullable=False),
        sa.Column("parser_rule_version", sa.String(100)),
        sa.Column("chunking_policy_version", sa.String(100)),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("search_schema_version", sa.String(100)),
        sa.Column("opensearch_analyzer_version", sa.String(100)),
        sa.Column("synonym_version", sa.String(100)),
        sa.Column("qdrant_collection", sa.String(100)),
        sa.Column("opensearch_index", sa.String(100)),
        sa.Column("qdrant_status", sa.String(50)),
        sa.Column("opensearch_status", sa.String(50)),
        sa.Column("created_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_reason_code", sa.String(100)),
        sa.Column("failed_reason_message", sa.Text()),
        sa.Column(
            "requested_by",
            sa.String(100),
            sa.ForeignKey("app.users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "reindex_scope IN ('INDEX_ONLY', 'CHUNK_AND_INDEX', 'KEYWORD_ONLY', 'VECTOR_ONLY')",
            name="ck_standard_reindex_jobs_scope",
        ),
        sa.CheckConstraint(
            "job_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED')",
            name="ck_standard_reindex_jobs_status",
        ),
        sa.CheckConstraint(
            "created_chunk_count >= 0 AND indexed_chunk_count >= 0",
            name="ck_standard_reindex_jobs_counts",
        ),
        schema="rag",
    )
    op.create_index(
        "idx_standard_reindex_jobs_standard",
        "standard_reindex_jobs",
        ["standard_id", "standard_version_id"],
        schema="rag",
    )
    op.create_index(
        "idx_standard_reindex_jobs_status",
        "standard_reindex_jobs",
        ["job_status"],
        schema="rag",
    )
    op.create_index(
        "idx_standard_reindex_jobs_requested_at",
        "standard_reindex_jobs",
        ["requested_at"],
        schema="rag",
    )

    op.execute("GRANT USAGE ON SCHEMA rag TO app, readonly")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA rag TO readonly")


def downgrade() -> None:
    for table_name in reversed(RAG_TABLES):
        op.drop_table(table_name, schema="rag")
