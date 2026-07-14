"""Create the schema-only M1 database base.

Revision ID: 0001_schema_only_base
Revises:
"""

from typing import Sequence

from alembic import op

revision: str = "0001_schema_only_base"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ("app", "rag", "validation", "audit")


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}" AUTHORIZATION migration')


def downgrade() -> None:
    # A schema may contain data owned by a later milestone. Destructive schema
    # removal belongs to backup/restore operations, not an M1 best-effort down.
    pass
