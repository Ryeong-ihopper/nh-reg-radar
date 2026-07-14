#!/usr/bin/env bash
set -Eeuo pipefail

if [[ -z "${NH_DB_MIGRATION_URL:-}" ]]; then
  printf 'NH_DB_MIGRATION_URL is required\n' >&2
  exit 64
fi
if [[ -n "${NH_DB_RUNTIME_URL:-}" && "$NH_DB_RUNTIME_URL" == "$NH_DB_MIGRATION_URL" ]]; then
  printf 'runtime and migration DSNs must use different identities\n' >&2
  exit 64
fi

exec alembic -c apps/backend/alembic.ini upgrade head

