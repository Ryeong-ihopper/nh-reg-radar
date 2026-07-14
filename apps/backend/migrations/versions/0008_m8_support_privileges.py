"""Grant runtime access to the durable M6 support tables.

Revision ID: 0008_m8_support_privileges
Revises: 0007_m7_validation_kpi
"""

from alembic import op


revision = "0008_m8_support_privileges"
down_revision = "0007_m7_validation_kpi"
branch_labels = None
depends_on = None

SUPPORT_TABLES = (
    "suggestions",
    "suggestion_decisions",
    "qa_sessions",
    "qa_messages",
    "qa_message_evidences",
    "opinion_drafts",
    "reports",
    "comparisons",
    "comparison_items",
)


def upgrade() -> None:
    tables = ", ".join(f"app.{table}" for table in SUPPORT_TABLES)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tables} TO app")
    op.execute(f"GRANT SELECT ON TABLE {tables} TO readonly")


def downgrade() -> None:
    tables = ", ".join(f"app.{table}" for table in SUPPORT_TABLES)
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {tables} FROM app, readonly")
