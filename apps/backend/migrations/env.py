from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def migration_url() -> str:
    url = os.environ.get("NH_DB_MIGRATION_URL", "")
    if not url:
        raise RuntimeError("NH_DB_MIGRATION_URL is required for Alembic")
    return url


def configure_context(connection=None, *, url: str | None = None) -> None:
    options = {
        "target_metadata": target_metadata,
        "version_table": "alembic_version",
        "version_table_schema": "app",
        "include_schemas": True,
        "compare_type": True,
    }
    if connection is None:
        context.configure(
            url=url, literal_binds=True, dialect_opts={"paramstyle": "named"}, **options
        )
    else:
        context.configure(connection=connection, **options)


def run_migrations_offline() -> None:
    configure_context(url=migration_url())
    context.execute("CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION migration")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = migration_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        identity = connection.execute(text("SELECT current_user")).scalar_one()
        if identity != "migration":
            raise RuntimeError(f"Alembic requires migration identity, got {identity!r}")

        # Alembic checks its version table before the first revision runs, so its
        # containing schema must be established inside this migration-only path.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION migration"))
        connection.commit()
        configure_context(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
