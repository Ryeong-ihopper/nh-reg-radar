#!/usr/bin/env bash
set -Eeuo pipefail

# This script is the only privileged PostgreSQL bootstrap boundary. Alembic must
# never create or alter roles; it runs later with the migration identity.

required=(
  NH_DB_APP_PASSWORD
  NH_DB_MIGRATION_PASSWORD
  NH_DB_READONLY_PASSWORD
  NH_DB_ADMIN_PASSWORD
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'missing required bootstrap variable: %s\n' "$name" >&2
    exit 64
  fi
done

database="${PGDATABASE:-${POSTGRES_DB:-}}"
if [[ -z "$database" ]]; then
  printf 'PGDATABASE or POSTGRES_DB is required\n' >&2
  exit 64
fi
bootstrap_user="${PGUSER:-${POSTGRES_USER:-postgres}}"
if [[ -z "${PGPASSWORD:-}" && -n "${POSTGRES_PASSWORD:-}" ]]; then
  export PGPASSWORD="$POSTGRES_PASSWORD"
fi

encode() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

app_password_b64="$(encode "$NH_DB_APP_PASSWORD")"
migration_password_b64="$(encode "$NH_DB_MIGRATION_PASSWORD")"
readonly_password_b64="$(encode "$NH_DB_READONLY_PASSWORD")"
admin_password_b64="$(encode "$NH_DB_ADMIN_PASSWORD")"

# Passwords travel only over psql stdin. They are not present in process args,
# generated SQL files, command output, images, or repository artifacts.
{
  printf "\\set app_password_b64 '%s'\n" "$app_password_b64"
  printf "\\set migration_password_b64 '%s'\n" "$migration_password_b64"
  printf "\\set readonly_password_b64 '%s'\n" "$readonly_password_b64"
  printf "\\set admin_password_b64 '%s'\n" "$admin_password_b64"
  cat <<'SQL'
SELECT format(
  'CREATE ROLE app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  convert_from(decode(:'app_password_b64', 'base64'), 'UTF8')
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') \gexec
SELECT format(
  'ALTER ROLE app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
) \gexec

SELECT format(
  'CREATE ROLE migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  convert_from(decode(:'migration_password_b64', 'base64'), 'UTF8')
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migration') \gexec
SELECT format(
  'ALTER ROLE migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
) \gexec

SELECT format(
  'CREATE ROLE readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  convert_from(decode(:'readonly_password_b64', 'base64'), 'UTF8')
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') \gexec
SELECT format(
  'ALTER ROLE readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
) \gexec

SELECT format(
  'CREATE ROLE admin LOGIN NOSUPERUSER CREATEDB CREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  convert_from(decode(:'admin_password_b64', 'base64'), 'UTF8')
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'admin') \gexec
SELECT format(
  'ALTER ROLE admin LOGIN NOSUPERUSER CREATEDB CREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
) \gexec

SELECT format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM app', current_database()) \gexec
SELECT format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM migration', current_database()) \gexec
SELECT format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM readonly', current_database()) \gexec
SELECT format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM admin', current_database()) \gexec
SELECT format('REVOKE CREATE ON SCHEMA public FROM PUBLIC') \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO app', current_database()) \gexec
SELECT format('GRANT CONNECT, CREATE, TEMPORARY ON DATABASE %I TO migration', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO readonly', current_database()) \gexec
SELECT format('GRANT CONNECT, CREATE, TEMPORARY ON DATABASE %I TO admin', current_database()) \gexec
SQL
} | psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --username "$bootstrap_user" --dbname "$database"

if [[ "${NH_DB_REVOKE_BOOTSTRAP_LOGIN:-false}" =~ ^(1|true|TRUE)$ ]]; then
  case "$bootstrap_user" in
    app|migration|readonly|admin)
      printf 'refusing to revoke a product identity as bootstrap: %s\n' "$bootstrap_user" >&2
      exit 1
      ;;
  esac
  cat <<'SQL' | psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --username "$bootstrap_user" --dbname "$database"
SELECT format('ALTER ROLE %I NOLOGIN', current_user) \gexec
SQL
  if psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --username "$bootstrap_user" --dbname "$database" --command 'SELECT 1' >/dev/null 2>&1; then
    printf 'revoked bootstrap credential was unexpectedly reusable\n' >&2
    exit 1
  fi
fi

unset app_password_b64 migration_password_b64 readonly_password_b64 admin_password_b64
unset NH_DB_APP_PASSWORD NH_DB_MIGRATION_PASSWORD NH_DB_READONLY_PASSWORD NH_DB_ADMIN_PASSWORD
unset PGPASSWORD POSTGRES_PASSWORD
