#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${NH_ENVIRONMENT:-}" != "dev" ]]; then
  printf 'dev seed is allowed only when NH_ENVIRONMENT=dev\n' >&2
  exit 64
fi

if [[ -z "${NH_DB_RUNTIME_URL:-}" ]]; then
  printf 'NH_DB_RUNTIME_URL is required\n' >&2
  exit 64
fi
if [[ -z "${NH_DEV_SEED_PASSWORD_HASH:-}" ]]; then
  printf 'NH_DEV_SEED_PASSWORD_HASH is required and must contain only a password hash\n' >&2
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
  printf 'dev seed requires app runtime identity, got %s\n' "$identity" >&2
  exit 64
fi

password_hash_b64="$(printf '%s' "$NH_DEV_SEED_PASSWORD_HASH" | base64 | tr -d '\n')"
unset NH_DEV_SEED_PASSWORD_HASH
psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
  --dbname "$(psql_url "$NH_DB_RUNTIME_URL")" \
  --set "dev_password_hash_b64=$password_hash_b64" \
  --file apps/backend/seeds/dev.sql
unset password_hash_b64
