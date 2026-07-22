"""Scope durable Q&A sessions to the review they support.

Revision ID: 0010_qa_review_sessions
Revises: 0009_operational_consistency
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_qa_review_sessions"
down_revision: str | None = "0009_operational_consistency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "qa_sessions",
        sa.Column(
            "review_id",
            sa.String(50),
            sa.ForeignKey("app.reviews.review_id", ondelete="CASCADE"),
            nullable=True,
        ),
        schema="rag",
    )
    op.create_index(
        "idx_qa_sessions_user_review_created",
        "qa_sessions",
        ["user_id", "review_id", "created_at"],
        schema="rag",
    )


def downgrade() -> None:
    op.drop_index("idx_qa_sessions_user_review_created", table_name="qa_sessions", schema="rag")
    op.drop_column("qa_sessions", "review_id", schema="rag")
