"""Grant runtime access to the durable M6 support tables.

Revision ID: 0008_m8_support_privileges
Revises: 0007_m7_validation_kpi
"""

from alembic import op


revision = "0008_m8_support_privileges"
down_revision = "0007_m7_validation_kpi"
branch_labels = None
depends_on = None

APP_SUPPORT_TABLES = (
    "suggestions",
    "suggestion_decisions",
    "opinion_drafts",
    "reports",
    "comparisons",
    "comparison_items",
)
RAG_SUPPORT_TABLES = ("qa_sessions", "qa_messages", "qa_message_evidences")


def _qualified_tables(schema: str, tables: tuple[str, ...]) -> str:
    return ", ".join(f"{schema}.{table}" for table in tables)


def upgrade() -> None:
    app_tables = _qualified_tables("app", APP_SUPPORT_TABLES)
    rag_tables = _qualified_tables("rag", RAG_SUPPORT_TABLES)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {app_tables}, {rag_tables} TO app")
    op.execute(f"GRANT SELECT ON TABLE {app_tables}, {rag_tables} TO readonly")


def downgrade() -> None:
    app_tables = _qualified_tables("app", APP_SUPPORT_TABLES)
    rag_tables = _qualified_tables("rag", RAG_SUPPORT_TABLES)
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {app_tables}, {rag_tables} FROM app, readonly")
