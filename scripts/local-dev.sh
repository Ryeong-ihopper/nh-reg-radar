#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

ENV_FILE="${NH_LOCAL_DEV_ENV_FILE:-.env.dev}"

usage() {
  cat <<'EOF'
Usage: scripts/local-dev.sh [--env-file FILE] COMMAND [SERVICE...]

Commands:
  up       Bootstrap, migrate, seed, build, and wait for the full dev stack
  status   Show Compose service status
  logs     Follow all logs, or only the named SERVICE logs
  down     Stop containers while preserving local data volumes
  reset    Delete this Compose project's volumes, then rebuild from an empty DB
  help     Show this help

Environment:
  NH_LOCAL_DEV_PASSWORD  Synthetic dev-user password (default: Testihopper12#$)
  NH_LOCAL_DEV_ENV_FILE  Alternative to --env-file (default: .env.dev)
EOF
}

if [[ "${1:-}" == "--env-file" ]]; then
  if [[ -z "${2:-}" ]]; then
    printf '%s\n' '--env-file requires a path' >&2
    exit 64
  fi
  ENV_FILE="$2"
  shift 2
fi

COMMAND="${1:-help}"
if (($# > 0)); then
  shift
fi

if [[ "$COMMAND" == "help" || "$COMMAND" == "--help" || "$COMMAND" == "-h" ]]; then
  usage
  exit 0
fi

case "$COMMAND" in
  up | status | logs | down | reset) ;;
  *)
    printf 'unknown command: %s\n' "$COMMAND" >&2
    usage >&2
    exit 64
    ;;
esac

if [[ "$ENV_FILE" != /* ]]; then
  ENV_FILE="$ROOT/$ENV_FILE"
fi
if [[ ! -f "$ENV_FILE" ]]; then
  printf 'local dev env file not found: %s\n' "$ENV_FILE" >&2
  printf '%s\n' 'create it with: cp .env.dev.example .env.dev' >&2
  exit 66
fi
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'required command not found: docker' >&2
  exit 69
fi
if ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' 'Docker Compose v2 plugin is required' >&2
  exit 69
fi

COMPOSE=(docker compose -f compose.yml -f compose.dev.yml --env-file "$ENV_FILE")
"${COMPOSE[@]}" config --quiet

if [[ "$COMMAND" == "status" ]]; then
  exec "${COMPOSE[@]}" ps
fi
if [[ "$COMMAND" == "logs" ]]; then
  exec "${COMPOSE[@]}" logs --follow --tail=200 "$@"
fi
if [[ "$COMMAND" == "down" ]]; then
  exec "${COMPOSE[@]}" down --remove-orphans
fi
if [[ "$COMMAND" == "reset" ]]; then
  "${COMPOSE[@]}" down --volumes --remove-orphans
  COMMAND="up"
fi

env_value() {
  local key="$1"
  local value
  value="$("${COMPOSE[@]}" config --environment | sed -n "s/^${key}=//p" | head -n 1)"
  if [[ -z "$value" ]]; then
    printf 'required dev environment value is empty: %s\n' "$key" >&2
    exit 65
  fi
  printf '%s' "$value"
}

postgres_db="$(env_value POSTGRES_DB)"
app_password="$(env_value NH_DB_APP_PASSWORD)"
migration_url="$(env_value NH_DB_MIGRATION_URL)"
runtime_url="$(env_value NH_DB_RUNTIME_URL)"
frontend_port="$(env_value FRONTEND_PORT)"
backend_port="$(env_value BACKEND_PORT)"
worker_port="$(env_value WORKER_PORT)"
minio_console_port="$(env_value MINIO_CONSOLE_PORT)"
local_password="${NH_LOCAL_DEV_PASSWORD:-Testihopper12#$}"
using_default_password=true
if [[ -n "${NH_LOCAL_DEV_PASSWORD:-}" ]]; then
  using_default_password=false
fi
if ((${#local_password} < 10)); then
  printf '%s\n' 'NH_LOCAL_DEV_PASSWORD must contain at least 10 characters' >&2
  exit 64
fi
if [[ "$migration_url" != */"$postgres_db" || "$runtime_url" != */"$postgres_db" ]]; then
  printf '%s\n' 'POSTGRES_DB must match the database name in both NH_DB URLs' >&2
  exit 65
fi

printf '%s\n' '[local-dev] starting PostgreSQL bootstrap'
"${COMPOSE[@]}" up --detach --wait postgres

printf '%s\n' '[local-dev] applying Alembic migrations with the migration identity'
"${COMPOSE[@]}" run --rm --no-deps --build \
  --env "NH_DB_MIGRATION_URL=$migration_url" \
  backend alembic -c alembic.ini upgrade head

printf '%s\n' '[local-dev] applying common seed with the app identity'
"${COMPOSE[@]}" exec -T \
  --env "PGPASSWORD=$app_password" \
  postgres psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
  --host=127.0.0.1 --username=app --dbname="$postgres_db" --file=- \
  < apps/backend/seeds/common.sql

printf '%s\n' '[local-dev] hashing and applying synthetic dev-user credentials'
password_hash_b64="$(
  printf '%s' "$local_password" \
    | "${COMPOSE[@]}" run --rm -T --no-deps backend python -c \
      'import base64, sys; from nh_ad_backend.security import hash_password; print(base64.b64encode(hash_password(sys.stdin.read()).encode()).decode())' \
    | tail -n 1
)"
if [[ ! "$password_hash_b64" =~ ^[A-Za-z0-9+/=]+$ ]]; then
  printf '%s\n' 'failed to generate the synthetic dev password hash' >&2
  exit 70
fi
unset local_password

"${COMPOSE[@]}" exec -T \
  --env "PGPASSWORD=$app_password" \
  postgres psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
  --host=127.0.0.1 --username=app --dbname="$postgres_db" \
  --set "dev_password_hash_b64=$password_hash_b64" --file=- \
  < apps/backend/seeds/dev.sql
unset password_hash_b64 app_password migration_url runtime_url

printf '%s\n' '[local-dev] building and waiting for the complete dev stack'
"${COMPOSE[@]}" up --detach --build --wait
"${COMPOSE[@]}" ps

cat <<EOF

Local development stack is ready.
  Frontend:       http://localhost:${frontend_port}
  Backend health: http://localhost:${backend_port}/health
  Backend OpenAPI: http://localhost:${backend_port}/openapi.json
  Worker ready:   http://localhost:${worker_port}/ready
  MinIO console:  http://localhost:${minio_console_port}

Synthetic users:
  test@ihopper.co.kr  (업무·기준자료 테스트)
  admin@ihopper.co.kr (시스템 관리자)
EOF
if [[ "$using_default_password" == true ]]; then
  printf '%s\n' '  Password: Testihopper12#$'
else
  printf '%s\n' '  Password: the value supplied through NH_LOCAL_DEV_PASSWORD'
fi
