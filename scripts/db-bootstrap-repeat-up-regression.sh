#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="${NH_G011_COMPOSE_PROJECT:-g011-repeat-$(date -u +%Y%m%d%H%M%S)-$$}"
timeout_seconds="${NH_G011_TIMEOUT_SECONDS:-120}"
compose=(
  docker compose
  --project-name "$project"
  --file "$root/compose.yml"
  --env-file "$root/.env.dev.example"
)

cleanup() {
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

compose_up_postgres() {
  timeout "$timeout_seconds" "${compose[@]}" up -d --wait postgres
}

query_postgres() {
  local database="$1"
  local sql="$2"
  "${compose[@]}" exec -T postgres \
    psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --username admin --dbname "$database" --command "$sql"
}

role_snapshot() {
  query_postgres nh_ad_dev \
    "SELECT rolname || ':' || rolcanlogin || ':' || rolsuper || ':' || rolcreatedb || ':' || rolcreaterole FROM pg_roles WHERE rolname IN ('app','migration','readonly','admin','nh_bootstrap') ORDER BY rolname;"
}

printf 'G011 fresh-volume bootstrap: project=%s\n' "$project"
compose_up_postgres

"${compose[@]}" exec -T postgres \
  createdb --username admin --owner admin g011_repeat_guard
query_postgres g011_repeat_guard \
  "CREATE TABLE g011_repeat_guard (id integer PRIMARY KEY, payload text NOT NULL); INSERT INTO g011_repeat_guard VALUES (1, 'repeat_guard_payload');" \
  >/dev/null

fresh_roles="$(role_snapshot)"
fresh_payload="$(query_postgres g011_repeat_guard "SELECT id || ':' || payload FROM g011_repeat_guard ORDER BY id;")"
fresh_checksum="$(printf '%s\n%s\n' "$fresh_roles" "$fresh_payload" | sha256sum | cut -d' ' -f1)"
fresh_bootstrap_id="$("${compose[@]}" ps -aq db-bootstrap)"
fresh_postgres_id="$("${compose[@]}" ps -q postgres)"

"${compose[@]}" rm --force --stop db-bootstrap >/dev/null
repeat_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'G011 existing-volume repeat up: project=%s\n' "$project"
compose_up_postgres

bootstrap_id="$("${compose[@]}" ps -aq db-bootstrap)"
postgres_id="$("${compose[@]}" ps -q postgres)"
if [[ "$bootstrap_id" == "$fresh_bootstrap_id" ]]; then
  printf '%s\n' 'repeat up did not recreate the db-bootstrap container' >&2
  exit 1
fi
if [[ "$postgres_id" != "$fresh_postgres_id" ]]; then
  printf '%s\n' 'repeat up unexpectedly recreated the running postgres container' >&2
  exit 1
fi
bootstrap_repeat_logs="$(docker logs --since "$repeat_started_at" "$bootstrap_id" 2>&1)"
postgres_repeat_logs="$(docker logs --since "$repeat_started_at" "$postgres_id" 2>&1)"

if ! grep -Fq \
  'active PostgreSQL volume detected; reused running postgres service without local server launch' \
  <<<"$bootstrap_repeat_logs"; then
  printf '%s\n' 'repeat bootstrap did not take the active-volume guard path' >&2
  exit 1
fi

if grep -Eiq \
  'PANIC|invalid checkpoint|database system was interrupted|automatic recovery in progress' \
  <<<"$bootstrap_repeat_logs"$'\n'"$postgres_repeat_logs"; then
  printf '%s\n' 'repeat up emitted PostgreSQL collision/recovery evidence' >&2
  exit 1
fi

repeat_roles="$(role_snapshot)"
repeat_payload="$(query_postgres g011_repeat_guard "SELECT id || ':' || payload FROM g011_repeat_guard ORDER BY id;")"
repeat_checksum="$(printf '%s\n%s\n' "$repeat_roles" "$repeat_payload" | sha256sum | cut -d' ' -f1)"

if [[ "$fresh_roles" != "$repeat_roles" ]]; then
  printf '%s\n' 'role or privilege identity drift detected after repeat up' >&2
  exit 1
fi
if [[ "$fresh_payload" != "1:repeat_guard_payload" || "$repeat_payload" != "$fresh_payload" ]]; then
  printf '%s\n' 'sentinel data changed or disappeared after repeat up' >&2
  exit 1
fi
if [[ "$repeat_checksum" != "$fresh_checksum" ]]; then
  printf '%s\n' 'fresh/repeat integrity checksum mismatch' >&2
  exit 1
fi

printf 'PASS: G011 fresh/repeat-volume bootstrap regression checksum=%s\n' "$repeat_checksum"
