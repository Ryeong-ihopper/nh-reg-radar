#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file=""
fresh_project=false
with_restart_and_outages=false
timeout_seconds="${NH_M8_RELEASE_TIMEOUT_SECONDS:-600}"
project="${NH_M8_RELEASE_COMPOSE_PROJECT:-m8-release-$(date -u +%Y%m%d%H%M%S)-$$}"
backup_dir=""

usage() {
  cat <<'EOF'
Usage: release-smoke.sh --env-file PATH --fresh-project --with-restart-and-outages

Runs the mandatory G011 live-volume regression first, then a uniquely named,
provider-free production Compose fresh start, migration/store recovery rehearsal,
graceful application restart, bounded dependency outages, and exact cleanup.
EOF
}

while (($#)); do
  case "$1" in
    --env-file)
      env_file="${2:?--env-file requires a value}"
      shift 2
      ;;
    --fresh-project)
      fresh_project=true
      shift
      ;;
    --with-restart-and-outages)
      with_restart_and_outages=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ -z "$env_file" || "$fresh_project" != true || "$with_restart_and_outages" != true ]]; then
  usage >&2
  exit 64
fi
if [[ ! "$project" =~ ^m8-release-[a-zA-Z0-9-]+$ ]]; then
  printf 'release project must be uniquely prefixed with m8-release-: %s\n' "$project" >&2
  exit 64
fi
env_file="$(cd "$(dirname "$env_file")" && pwd)/$(basename "$env_file")"
backup_dir="$(mktemp -d "${TMPDIR:-/tmp}/${project}.XXXXXX")"

compose=(
  docker compose
  --project-name "$project"
  --file "$root/compose.yml"
  --file "$root/compose.prod.yml"
  --env-file "$env_file"
)

project_resources() {
  {
    docker ps -aq --filter "label=com.docker.compose.project=$1"
    docker volume ls -q --filter "label=com.docker.compose.project=$1"
    docker network ls -q --filter "label=com.docker.compose.project=$1"
  } | sed '/^$/d'
}

cleanup() {
  local exit_code=$?
  trap - EXIT
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$backup_dir"
  if [[ -n "$(project_resources "$project")" ]]; then
    printf 'release recovery resources remain after cleanup: %s\n' "$project" >&2
    docker ps -a --filter "label=com.docker.compose.project=$project" >&2 || true
    docker volume ls --filter "label=com.docker.compose.project=$project" >&2 || true
    docker network ls --filter "label=com.docker.compose.project=$project" >&2 || true
    exit_code=1
  fi
  exit "$exit_code"
}
trap cleanup EXIT

wait_for_service_health() {
  local service="$1"
  local deadline=$((SECONDS + timeout_seconds))
  local container_id health
  while ((SECONDS < deadline)); do
    container_id="$("${compose[@]}" ps -q "$service")"
    if [[ -n "$container_id" ]]; then
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
      if [[ "$health" == healthy || "$health" == running ]]; then
        return 0
      fi
    fi
    sleep 2
  done
  printf 'service did not become healthy within %ss: %s\n' "$timeout_seconds" "$service" >&2
  "${compose[@]}" ps >&2 || true
  return 1
}

wait_for_worker_not_ready() {
  local deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if "${compose[@]}" exec -T worker python - <<'PY' >/dev/null 2>&1
import urllib.error
import urllib.request

try:
    urllib.request.urlopen("http://127.0.0.1:8001/ready", timeout=2)
except urllib.error.HTTPError as exc:
    raise SystemExit(0 if exc.code == 503 else 1)
except OSError:
    raise SystemExit(1)
raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 1
  done
  printf '%s\n' 'worker did not report not-ready during the bounded Redis outage' >&2
  return 1
}

run_g011_gate() {
  local started elapsed g011_project
  g011_project="${project}-g011"
  started=$SECONDS
  NH_RUN_G011_DOCKER_REGRESSION=1 \
    NH_G011_COMPOSE_PROJECT="$g011_project" \
    NH_G011_TIMEOUT_SECONDS=120 \
    PYTHONPATH=. \
    uv run pytest tests/integration/test_compose_bootstrap_repeat_up.py -q
  elapsed=$((SECONDS - started))
  if ((elapsed > 120)); then
    printf 'G011 cold gate exceeded 120s: %ss\n' "$elapsed" >&2
    exit 1
  fi
  if [[ -n "$(project_resources "$g011_project")" ]]; then
    printf 'G011 resources remain after its cleanup: %s\n' "$g011_project" >&2
    exit 1
  fi
  printf 'G011_COLD_GATE_SECONDS=%s\n' "$elapsed"
}

run_fresh_start() {
  local started elapsed
  if [[ -n "$(project_resources "$project")" ]]; then
    printf 'fresh release project already has Docker resources: %s\n' "$project" >&2
    exit 1
  fi
  "${compose[@]}" config --quiet
  "${compose[@]}" build frontend backend worker
  started=$SECONDS
  timeout "$timeout_seconds" "${compose[@]}" up -d --wait
  elapsed=$((SECONDS - started))
  for service in frontend backend worker postgres redis minio qdrant opensearch; do
    wait_for_service_health "$service"
  done
  printf 'PROD_COLD_START_SECONDS=%s\n' "$elapsed"
}

run_restart_and_outages() {
  printf '%s\n' 'M8 graceful application restart'
  "${compose[@]}" stop frontend backend worker
  "$root/scripts/release-recovery-rehearsal.sh" \
    --project "$project" \
    --env-file "$env_file" \
    --backup-dir "$backup_dir"
  "${compose[@]}" up -d --wait frontend backend worker
  for service in frontend backend worker; do
    wait_for_service_health "$service"
  done

  printf '%s\n' 'M8 bounded Redis outage and readiness recovery'
  "${compose[@]}" stop redis
  wait_for_worker_not_ready
  "${compose[@]}" start redis
  wait_for_service_health redis
  wait_for_service_health worker

  printf '%s\n' 'M8 bounded object/search outages and recovery'
  for service in minio qdrant opensearch; do
    "${compose[@]}" stop "$service"
    if [[ "$(docker inspect --format '{{.State.Running}}' "$("${compose[@]}" ps -aq "$service")")" != false ]]; then
      printf 'dependency did not stop: %s\n' "$service" >&2
      exit 1
    fi
    "${compose[@]}" start "$service"
    wait_for_service_health "$service"
  done

  printf '%s\n' 'M8 PostgreSQL restart after G011 live-volume proof'
  "${compose[@]}" restart postgres
  wait_for_service_health postgres
  "${compose[@]}" exec -T postgres psql --no-psqlrc --quiet --tuples-only --no-align \
    --set=ON_ERROR_STOP=1 --username migration --dbname "$(awk -F= '$1 == "POSTGRES_DB" {print $2; exit}' "$env_file")" \
    --command 'SELECT version_num FROM app.alembic_version;' \
    | grep -qx 0008_m8_support_privileges
}

run_g011_gate
run_fresh_start
run_restart_and_outages

manifest_checksum="$(sha256sum "$backup_dir/manifest.json" | cut -d' ' -f1)"
printf 'PASS: M8 production fresh/restart/outage smoke project=%s manifest_sha256=%s\n' \
  "$project" "$manifest_checksum"
