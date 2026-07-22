#!/usr/bin/env bash
set -Eeuo pipefail

required=(NH_DB_MIGRATION_URL NH_DB_RUNTIME_URL NH_DB_READONLY_URL)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'missing required probe variable: %s\n' "$name" >&2
    exit 64
  fi
done
if [[ "$NH_DB_RUNTIME_URL" == "$NH_DB_MIGRATION_URL" ]]; then
  printf 'runtime and migration DSNs are identical\n' >&2
  exit 1
fi

psql_url() {
  local url="$1"
  url="${url/postgresql+psycopg:/postgresql:}"
  url="${url/postgresql+psycopg2:/postgresql:}"
  printf '%s' "$url"
}

query() {
  psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --tuples-only --no-align --dbname "$(psql_url "$1")" --command "$2"
}

expect_denied() {
  local url="$1" sql="$2" label="$3"
  local output
  if output="$(psql --no-psqlrc --set=ON_ERROR_STOP=1 --dbname "$(psql_url "$url")" --command "$sql" 2>&1)"; then
    printf 'unexpected privilege allowed: %s\n' "$label" >&2
    exit 1
  fi
  if ! grep -Eqi 'permission denied|must be|not permitted' <<<"$output"; then
    printf 'probe failed for a reason other than privilege denial (%s): %s\n' "$label" "$output" >&2
    exit 1
  fi
  printf 'PASS: denied %s\n' "$label"
}

[[ "$(query "$NH_DB_MIGRATION_URL" 'SELECT current_user')" == "migration" ]]
[[ "$(query "$NH_DB_RUNTIME_URL" 'SELECT current_user')" == "app" ]]
[[ "$(query "$NH_DB_READONLY_URL" 'SELECT current_user')" == "readonly" ]]

schema_count="$(query "$NH_DB_MIGRATION_URL" "SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('app','rag','validation','audit')")"
[[ "$schema_count" == "4" ]]
migration_revision="$(query "$NH_DB_MIGRATION_URL" 'SELECT version_num FROM app.alembic_version')"
[[ "$migration_revision" == "0010_qa_review_sessions" ]]
expected_relation_count="$(query "$NH_DB_MIGRATION_URL" "SELECT count(*) FROM (VALUES ('app.users'), ('app.ocr_text_blocks'), ('rag.evidences'), ('validation.validation_datasets'), ('audit.audit_logs')) AS expected(relation_name) WHERE to_regclass(relation_name) IS NOT NULL")"
[[ "$expected_relation_count" == "5" ]]

expect_denied "$NH_DB_MIGRATION_URL" 'CREATE ROLE privilege_probe_migration' 'migration CREATE ROLE'
expect_denied "$NH_DB_MIGRATION_URL" 'ALTER ROLE app CREATEDB' 'migration ALTER ROLE'
expect_denied "$NH_DB_RUNTIME_URL" 'CREATE TABLE app.privilege_probe(id integer)' 'app DDL'
expect_denied "$NH_DB_RUNTIME_URL" 'CREATE ROLE privilege_probe_app' 'app role management'
expect_denied "$NH_DB_READONLY_URL" "INSERT INTO app.alembic_version(version_num) VALUES ('forbidden')" 'readonly INSERT'
expect_denied "$NH_DB_READONLY_URL" "UPDATE app.alembic_version SET version_num='forbidden'" 'readonly UPDATE'
expect_denied "$NH_DB_READONLY_URL" 'DELETE FROM app.alembic_version' 'readonly DELETE'
expect_denied "$NH_DB_READONLY_URL" 'CREATE TABLE app.privilege_probe(id integer)' 'readonly DDL'

printf 'PASS: database least-privilege matrix\n'
