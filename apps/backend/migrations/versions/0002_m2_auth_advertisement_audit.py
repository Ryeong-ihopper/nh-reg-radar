"""Create the M2 auth, advertisement, file, and audit owner tables.

Revision ID: 0002_m2_auth_advertisement_audit
Revises: 0001_schema_only_base
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_m2_auth_advertisement_audit"
down_revision: str | None = "0001_schema_only_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_TABLES = (
    "departments",
    "roles",
    "users",
    "user_roles",
    "refresh_tokens",
    "common_codes",
    "advertisements",
    "advertisement_revisions",
    "advertisement_files",
)


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("department_id", sa.String(50), primary_key=True),
        sa.Column("department_name", sa.String(200), nullable=False),
        sa.Column(
            "parent_department_id",
            sa.String(50),
            sa.ForeignKey("app.departments.department_id", ondelete="SET NULL"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.create_index("idx_departments_parent", "departments", ["parent_department_id"], schema="app")
    op.create_index("idx_departments_active", "departments", ["is_active"], schema="app")

    op.create_table(
        "roles",
        sa.Column("role_id", sa.String(50), primary_key=True),
        sa.Column("role_name", sa.String(100), nullable=False),
        sa.Column("role_description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="app",
    )

    op.create_table(
        "users",
        sa.Column("user_id", sa.String(100), primary_key=True),
        sa.Column("auth_provider", sa.String(50), nullable=False),
        sa.Column("external_subject", sa.String(255)),
        sa.Column("user_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255)),
        sa.Column(
            "department_id",
            sa.String(50),
            sa.ForeignKey("app.departments.department_id"),
            nullable=False,
        ),
        sa.Column("user_status", sa.String(30), nullable=False),
        sa.Column("auth_token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True)),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count"),
        sa.UniqueConstraint("email", name="uk_users_email"),
        sa.UniqueConstraint("auth_provider", "external_subject", name="uk_users_auth_subject"),
        schema="app",
    )
    op.create_index("idx_users_locked_until", "users", ["locked_until"], schema="app")

    op.create_table(
        "user_roles",
        sa.Column("user_role_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(100),
            sa.ForeignKey("app.users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.String(50),
            sa.ForeignKey("app.roles.role_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "role_id", name="uk_user_roles"),
        schema="app",
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("refresh_token_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(100),
            sa.ForeignKey("app.users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.String(50)),
        sa.Column("created_ip", sa.String(100)),
        sa.Column("user_agent", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("token_hash", name="uk_refresh_tokens_hash"),
        schema="app",
    )
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"], schema="app")
    op.create_index("idx_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], schema="app")
    op.create_index(
        "idx_refresh_tokens_active",
        "refresh_tokens",
        ["user_id", "revoked_at", "expires_at"],
        schema="app",
    )

    op.create_table(
        "common_codes",
        sa.Column("code_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_group", sa.String(100), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("code_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code_group", "code", name="uk_common_codes"),
        schema="app",
    )

    op.create_table(
        "advertisements",
        sa.Column("advertisement_id", sa.String(50), primary_key=True),
        sa.Column("advertisement_name", sa.String(300), nullable=False),
        sa.Column("product_group", sa.String(50), nullable=False),
        sa.Column("advertisement_type", sa.String(50), nullable=False),
        sa.Column("channel_type", sa.String(50)),
        sa.Column(
            "department_id",
            sa.String(50),
            sa.ForeignKey("app.departments.department_id"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(100),
            sa.ForeignKey("app.users.user_id"),
            nullable=False,
        ),
        sa.Column("review_status", sa.String(50), nullable=False),
        sa.Column("overall_risk_level", sa.String(50)),
        # M3+ owns the reviews table and adds the deferred FK when that table exists.
        sa.Column("latest_review_id", sa.String(50)),
        sa.Column("memo", sa.Text()),
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="app",
    )
    op.create_index("idx_advertisements_status", "advertisements", ["review_status"], schema="app")
    op.create_index(
        "idx_advertisements_product_type",
        "advertisements",
        ["product_group", "advertisement_type"],
        schema="app",
    )
    op.create_index("idx_advertisements_owner", "advertisements", ["owner_user_id"], schema="app")
    op.create_index("idx_advertisements_created_at", "advertisements", ["created_at"], schema="app")
    op.create_index(
        "idx_advertisements_latest_review",
        "advertisements",
        ["latest_review_id"],
        schema="app",
    )

    op.create_table(
        "advertisement_revisions",
        sa.Column("revision_id", sa.String(50), primary_key=True),
        sa.Column(
            "advertisement_id",
            sa.String(50),
            sa.ForeignKey("app.advertisements.advertisement_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        # M3+ owns the reviews table and adds the deferred FK when that table exists.
        sa.Column("base_review_id", sa.String(50)),
        sa.Column("revision_memo", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_by",
            sa.String(100),
            sa.ForeignKey("app.users.user_id"),
            nullable=False,
        ),
        sa.CheckConstraint("revision_no > 0", name="ck_ad_revision_no"),
        sa.UniqueConstraint("advertisement_id", "revision_no", name="uk_ad_revision_no"),
        schema="app",
    )

    op.create_table(
        "advertisement_files",
        sa.Column("file_id", sa.String(50), primary_key=True),
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
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("original_file_name", sa.String(500), nullable=False),
        sa.Column("storage_provider", sa.String(50), nullable=False),
        sa.Column("bucket", sa.String(255), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("preview_status", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_by",
            sa.String(100),
            sa.ForeignKey("app.users.user_id"),
            nullable=False,
        ),
        sa.CheckConstraint("file_size >= 0 AND file_size <= 52428800", name="ck_ad_file_size"),
        schema="app",
    )
    op.create_index(
        "idx_ad_files_advertisement", "advertisement_files", ["advertisement_id"], schema="app"
    )
    op.create_index("idx_ad_files_revision", "advertisement_files", ["revision_id"], schema="app")
    op.create_index("idx_ad_files_type", "advertisement_files", ["file_type"], schema="app")
    op.create_index(
        "idx_ad_files_checksum", "advertisement_files", ["checksum_sha256"], schema="app"
    )

    op.create_table(
        "audit_logs",
        sa.Column("audit_log_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", sa.String(100), sa.ForeignKey("app.users.user_id", ondelete="SET NULL")
        ),
        sa.Column(
            "actor_department_id",
            sa.String(50),
            sa.ForeignKey("app.departments.department_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "actor_role",
            sa.String(50),
            sa.ForeignKey("app.roles.role_id", ondelete="SET NULL"),
        ),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(100)),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("request_id", sa.String(100)),
        sa.Column("ip_address", sa.String(100)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("before_json", postgresql.JSONB()),
        sa.Column("after_json", postgresql.JSONB()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "result IN ('SUCCESS', 'FAILURE', 'DENIED')", name="ck_audit_logs_result"
        ),
        schema="audit",
    )
    op.create_index("idx_audit_logs_user", "audit_logs", ["user_id"], schema="audit")
    op.create_index(
        "idx_audit_logs_actor_department",
        "audit_logs",
        ["actor_department_id"],
        schema="audit",
    )
    op.create_index("idx_audit_logs_action", "audit_logs", ["action_type"], schema="audit")
    op.create_index(
        "idx_audit_logs_target", "audit_logs", ["target_type", "target_id"], schema="audit"
    )
    op.create_index("idx_audit_logs_result", "audit_logs", ["result"], schema="audit")
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"], schema="audit")

    op.execute("GRANT USAGE ON SCHEMA app, audit TO app, readonly")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app, audit TO app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA app, audit TO readonly")


def downgrade() -> None:
    op.drop_table("audit_logs", schema="audit")
    for table_name in reversed(APP_TABLES):
        op.drop_table(table_name, schema="app")
