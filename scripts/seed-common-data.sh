#!/usr/bin/env bash
set -Eeuo pipefail

if [[ -z "${NH_DB_RUNTIME_URL:-}" ]]; then
  printf 'NH_DB_RUNTIME_URL is required\n' >&2
  exit 64
fi

psql_url() {
  printf '%s' "${1/postgresql+psycopg:/postgresql:}"
}

identity="$(
  psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --dbname "$(psql_url "$NH_DB_RUNTIME_URL")" --command 'SELECT current_user'
)"
if [[ "$identity" != "app" ]]; then
  printf 'common seed requires app runtime identity, got %s\n' "$identity" >&2
  exit 64
fi

exec psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
  --dbname "$(psql_url "$NH_DB_RUNTIME_URL")" \
  --file apps/backend/seeds/common.sql
