"""Align OCR coordinates and text search with the database specification.

Revision ID: 0009_operational_consistency
Revises: 0008_m8_support_privileges
"""

import sqlalchemy as sa
from alembic import op


revision = "0009_operational_consistency"
down_revision = "0008_m8_support_privileges"
branch_labels = None
depends_on = None

COORDINATE_TABLES = ("ocr_text_blocks", "layout_blocks")
COORDINATE_RENAMES = (
    ("coordinate_x", "x"),
    ("coordinate_y", "y"),
    ("coordinate_width", "width"),
    ("coordinate_height", "height"),
)
NORMALIZED_COLUMNS = ("normalized_x", "normalized_y", "normalized_width", "normalized_height")


def upgrade() -> None:
    for table in COORDINATE_TABLES:
        for old_name, new_name in COORDINATE_RENAMES:
            op.alter_column(table, old_name, new_column_name=new_name, schema="app")
        for column in NORMALIZED_COLUMNS:
            op.alter_column(
                table,
                column,
                type_=sa.Numeric(8, 7),
                existing_type=sa.Numeric(8, 6),
                postgresql_using=f"{column}::numeric(8,7)",
                schema="app",
            )
        op.alter_column(
            table,
            "rotation",
            type_=sa.Numeric(6, 2),
            existing_type=sa.Numeric(8, 4),
            postgresql_using="rotation::numeric(6,2)",
            schema="app",
        )
    op.execute(
        "CREATE INDEX idx_ocr_blocks_text_gin ON app.ocr_text_blocks "
        "USING gin (to_tsvector('simple', coalesce(normalized_text, '')))"
    )


def downgrade() -> None:
    op.drop_index("idx_ocr_blocks_text_gin", table_name="ocr_text_blocks", schema="app")
    for table in reversed(COORDINATE_TABLES):
        op.alter_column(
            table,
            "rotation",
            type_=sa.Numeric(8, 4),
            existing_type=sa.Numeric(6, 2),
            postgresql_using="rotation::numeric(8,4)",
            schema="app",
        )
        for column in NORMALIZED_COLUMNS:
            op.alter_column(
                table,
                column,
                type_=sa.Numeric(8, 6),
                existing_type=sa.Numeric(8, 7),
                postgresql_using=f"{column}::numeric(8,6)",
                schema="app",
            )
        for old_name, new_name in reversed(COORDINATE_RENAMES):
            op.alter_column(table, new_name, new_column_name=old_name, schema="app")
