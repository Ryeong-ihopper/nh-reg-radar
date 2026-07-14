#!/usr/bin/env bash
set -Eeuo pipefail

required=(
  NH_DB_APP_PASSWORD
  NH_DB_MIGRATION_PASSWORD
  NH_DB_READONLY_PASSWORD
  NH_DB_ADMIN_PASSWORD
  PGDATABASE
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'missing required bootstrap probe variable: %s\n' "$name" >&2
    exit 64
  fi
done

snapshot() {
  psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 <<'SQL' | sha256sum | cut -d' ' -f1
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname IN ('app', 'migration', 'readonly', 'admin')
ORDER BY rolname;
SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE grantee IN ('app', 'migration', 'readonly', 'admin')
ORDER BY grantee, privilege_type;
SELECT role_name, privilege_type
FROM (VALUES ('app'), ('migration'), ('readonly'), ('admin')) AS roles(role_name)
CROSS JOIN (VALUES ('CONNECT'), ('CREATE'), ('TEMPORARY')) AS privileges(privilege_type)
WHERE has_database_privilege(role_name, current_database(), privilege_type)
ORDER BY role_name, privilege_type;
SQL
}

NH_DB_REVOKE_BOOTSTRAP_LOGIN=false infra/postgres/init/010-bootstrap-roles.sh
before="$(snapshot)"
NH_DB_REVOKE_BOOTSTRAP_LOGIN=false infra/postgres/init/010-bootstrap-roles.sh
after="$(snapshot)"
if [[ "$before" != "$after" ]]; then
  printf 'bootstrap role/grant drift detected\n' >&2
  exit 1
fi

count="$(psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command "SELECT count(*) FROM pg_roles WHERE rolname IN ('app','migration','readonly','admin')")"
[[ "$count" == "4" ]]

# The probe credential is intentionally one-shot. The current session may
# revoke its own future logins; a new connection with the same credential must
# then fail before the secret is removed from the job environment.
bootstrap_identity="$(psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command 'SELECT current_user')"
case "$bootstrap_identity" in
  app|migration|readonly|admin)
    printf 'bootstrap probe must not use a product identity: %s\n' "$bootstrap_identity" >&2
    exit 1
    ;;
esac
psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 <<'SQL'
SELECT format('ALTER ROLE %I NOLOGIN', current_user) \gexec
SQL
if psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --command 'SELECT 1' >/dev/null 2>&1; then
  printf 'revoked bootstrap credential was unexpectedly reusable\n' >&2
  exit 1
fi

unset PGPASSWORD POSTGRES_PASSWORD
unset NH_DB_APP_PASSWORD NH_DB_MIGRATION_PASSWORD NH_DB_READONLY_PASSWORD NH_DB_ADMIN_PASSWORD
printf 'PASS: idempotent PostgreSQL role bootstrap and credential revocation\n'
