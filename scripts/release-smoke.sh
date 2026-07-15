#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file=""
fresh_project=false
with_restart_and_outages=false
timeout_seconds="${NH_M8_RELEASE_TIMEOUT_SECONDS:-600}"
probe_timeout_seconds="${NH_M8_RELEASE_PROBE_TIMEOUT_SECONDS:-10}"
cleanup_timeout_seconds="${NH_M8_RELEASE_CLEANUP_TIMEOUT_SECONDS:-60}"
timeout_kill_after_seconds="${NH_M8_RELEASE_KILL_AFTER_SECONDS:-10}"
project="${NH_M8_RELEASE_COMPOSE_PROJECT:-m8-release-$(date -u +%Y%m%d%H%M%S)-$$}"
backup_dir=""
cleanup_started=false
cleanup_project_resources=false
active_timeout_pid=""

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

compose=(
  docker compose
  --project-name "$project"
  --file "$root/compose.yml"
  --file "$root/compose.prod.yml"
  --env-file "$env_file"
)
g011_project="${project}-g011"
g011_compose=(
  docker compose
  --project-name "$g011_project"
  --file "$root/compose.yml"
  --env-file "$root/.env.dev.example"
)

run_with_timeout() {
  local limit="$1"
  local command_status
  shift
  timeout --signal=TERM --kill-after="$timeout_kill_after_seconds" "$limit" "$@" &
  active_timeout_pid=$!
  if wait "$active_timeout_pid"; then
    command_status=0
  else
    command_status=$?
  fi
  active_timeout_pid=""
  return "$command_status"
}

compose_call_with_timeout() {
  local limit="$1"
  shift
  run_with_timeout "$limit" "${compose[@]}" "$@"
}

compose_call() {
  compose_call_with_timeout "$timeout_seconds" "$@"
}

compose_probe_call() {
  compose_call_with_timeout "$probe_timeout_seconds" "$@"
}

docker_probe_call() {
  run_with_timeout "$probe_timeout_seconds" docker "$@"
}

cleanup_compose_call() {
  run_with_timeout "$cleanup_timeout_seconds" "${compose[@]}" "$@"
}

cleanup_g011_compose_call() {
  run_with_timeout "$cleanup_timeout_seconds" "${g011_compose[@]}" "$@"
}

cleanup_docker_call() {
  run_with_timeout "$cleanup_timeout_seconds" docker "$@"
}

project_resources() {
  local project_name="$1"
  local docker_runner="${2:-docker_probe_call}"
  {
    "$docker_runner" ps -aq --filter "label=com.docker.compose.project=$project_name" || return
    "$docker_runner" volume ls -q --filter "label=com.docker.compose.project=$project_name" || return
    "$docker_runner" network ls -q --filter "label=com.docker.compose.project=$project_name" || return
  } | sed '/^$/d'
}

cleanup() {
  local exit_code=$?
  local resources resource_status
  if [[ "$cleanup_started" == true ]]; then
    return
  fi
  cleanup_started=true
  trap - EXIT
  trap '' INT TERM
  set +e
  if [[ -d "$backup_dir" ]]; then
    cleanup_docker_call run --rm \
      --volume "$backup_dir:/cleanup" \
      --entrypoint /bin/sh \
      minio/mc:RELEASE.2025-07-21T05-28-08Z \
      -ec 'chmod -R a+rwX /cleanup' >/dev/null 2>&1
  fi
  if [[ "$cleanup_project_resources" == true ]]; then
    cleanup_g011_compose_call down --volumes --remove-orphans >/dev/null 2>&1 || true
    cleanup_compose_call down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  if ! run_with_timeout "$cleanup_timeout_seconds" rm -rf "$backup_dir"; then
    if ((exit_code == 0)); then
      exit_code=1
    fi
  fi
  if [[ -e "$backup_dir" ]]; then
    printf 'release backup directory remains after cleanup: %s\n' "$backup_dir" >&2
    if ((exit_code == 0)); then
      exit_code=1
    fi
  fi
  if [[ "$cleanup_project_resources" == true ]]; then
    resources="$(project_resources "$project" cleanup_docker_call)"
    resource_status=$?
    if ((resource_status != 0)); then
      printf 'could not verify release recovery cleanup: %s\n' "$project" >&2
      if ((exit_code == 0)); then
        exit_code=1
      fi
    elif [[ -n "$resources" ]]; then
      printf 'release recovery resources remain after cleanup: %s\n' "$project" >&2
      cleanup_docker_call ps -a --filter "label=com.docker.compose.project=$project" >&2 || true
      cleanup_docker_call volume ls --filter "label=com.docker.compose.project=$project" >&2 || true
      cleanup_docker_call network ls --filter "label=com.docker.compose.project=$project" >&2 || true
      if ((exit_code == 0)); then
        exit_code=1
      fi
    fi
    resources="$(project_resources "$g011_project" cleanup_docker_call)"
    resource_status=$?
    if ((resource_status != 0)); then
      printf 'could not verify G011 cleanup: %s\n' "$g011_project" >&2
      if ((exit_code == 0)); then
        exit_code=1
      fi
    elif [[ -n "$resources" ]]; then
      printf 'G011 resources remain after outer cleanup: %s\n' "$g011_project" >&2
      cleanup_docker_call ps -a --filter "label=com.docker.compose.project=$g011_project" >&2 || true
      cleanup_docker_call volume ls --filter "label=com.docker.compose.project=$g011_project" >&2 || true
      cleanup_docker_call network ls --filter "label=com.docker.compose.project=$g011_project" >&2 || true
      if ((exit_code == 0)); then
        exit_code=1
      fi
    fi
  fi
  exit "$exit_code"
}

handle_signal() {
  local signal="$1"
  local signal_exit_code
  case "$signal" in
    INT) signal_exit_code=130 ;;
    TERM) signal_exit_code=143 ;;
    *) signal_exit_code=1 ;;
  esac
  trap '' INT TERM
  if [[ -n "$active_timeout_pid" ]]; then
    kill -TERM -- "-$active_timeout_pid" >/dev/null 2>&1 \
      || kill -TERM "$active_timeout_pid" >/dev/null 2>&1 \
      || true
    wait "$active_timeout_pid" >/dev/null 2>&1 || true
    active_timeout_pid=""
  fi
  exit "$signal_exit_code"
}

trap cleanup EXIT
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM
backup_dir="$(mktemp -d "${TMPDIR:-/tmp}/${project}.XXXXXX")"

assert_fresh_project() {
  local project_name resources
  for project_name in "$project" "$g011_project"; do
    resources="$(project_resources "$project_name")"
    if [[ -n "$resources" ]]; then
      printf 'fresh release project already has Docker resources: %s\n' "$project_name" >&2
      return 1
    fi
  done
}

wait_for_service_health() {
  local service="$1"
  local deadline=$((SECONDS + timeout_seconds))
  local container_id health
  while ((SECONDS < deadline)); do
    container_id="$(compose_probe_call ps -q "$service")"
    if [[ -n "$container_id" ]]; then
      health="$(docker_probe_call inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
      if [[ "$health" == healthy || "$health" == running ]]; then
        return 0
      fi
    fi
    sleep 2
  done
  printf 'service did not become healthy within %ss: %s\n' "$timeout_seconds" "$service" >&2
  compose_probe_call ps >&2 || true
  return 1
}

wait_for_worker_not_ready() {
  local deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if compose_probe_call exec -T worker python - <<'PY' >/dev/null 2>&1
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
  local started elapsed fresh_elapsed g011_log g011_status replay_status
  g011_log="$backup_dir/g011-regression.log"
  started=$SECONDS
  if run_with_timeout "$timeout_seconds" \
    env NH_RUN_G011_DOCKER_REGRESSION=1 \
      NH_G011_COMPOSE_PROJECT="$g011_project" \
      NH_G011_TIMEOUT_SECONDS=120 \
      PYTHONPATH=. \
      uv run pytest tests/integration/test_compose_bootstrap_repeat_up.py -q -s \
    >"$g011_log"; then
    g011_status=0
  else
    g011_status=$?
  fi
  if cat "$g011_log"; then
    replay_status=0
  else
    replay_status=$?
    printf 'could not replay G011 regression log: %s\n' "$g011_log" >&2
  fi
  if ((g011_status != 0)); then
    printf 'G011 full regression failed with status %s within %ss\n' \
      "$g011_status" "$timeout_seconds" >&2
    exit "$g011_status"
  fi
  if ((replay_status != 0)); then
    printf 'G011 regression log replay failed with status %s\n' "$replay_status" >&2
    exit "$replay_status"
  fi
  elapsed=$((SECONDS - started))
  fresh_elapsed="$(sed -n 's/^G011_FRESH_VOLUME_SECONDS=//p' "$g011_log" | tail -n 1)"
  if [[ ! "$fresh_elapsed" =~ ^[0-9]+$ ]] || ((fresh_elapsed > 120)); then
    printf 'G011 fresh-volume timing evidence missing or invalid: %s\n' "$fresh_elapsed" >&2
    exit 1
  fi
  if [[ -n "$(project_resources "$g011_project")" ]]; then
    printf 'G011 resources remain after its cleanup: %s\n' "$g011_project" >&2
    exit 1
  fi
  printf 'G011_COLD_GATE_SECONDS=%s\n' "$fresh_elapsed"
  printf 'G011_REGRESSION_SECONDS=%s\n' "$elapsed"
}

run_fresh_start() {
  local started postgres_elapsed elapsed
  compose_call config --quiet
  compose_call build frontend backend worker

  # A fresh PostgreSQL volume owns the one-time bootstrap critical path. Start
  # it before memory-heavy search services so the proven 120-second G011 bound
  # is meaningful rather than being distorted by concurrent image cold starts.
  started=$SECONDS
  compose_call_with_timeout 120 up -d --wait postgres
  postgres_elapsed=$((SECONDS - started))
  if ((postgres_elapsed > 120)); then
    printf 'G011 fresh-volume bootstrap exceeded 120s: %ss\n' "$postgres_elapsed" >&2
    exit 1
  fi
  wait_for_service_health postgres
  printf 'G011_FRESH_VOLUME_SECONDS=%s\n' "$postgres_elapsed"

  started=$SECONDS
  compose_call up -d --wait
  elapsed=$((SECONDS - started))
  for service in frontend backend worker postgres redis minio qdrant opensearch; do
    wait_for_service_health "$service"
  done
  printf 'PROD_COLD_START_SECONDS=%s\n' "$((postgres_elapsed + elapsed))"
}

run_restart_and_outages() {
  local container_id database_name migration_revision
  printf '%s\n' 'M8 graceful application restart'
  compose_call stop frontend backend worker
  run_with_timeout "$timeout_seconds" "$root/scripts/release-recovery-rehearsal.sh" \
    --project "$project" \
    --env-file "$env_file" \
    --backup-dir "$backup_dir"
  compose_call up -d --wait frontend backend worker
  for service in frontend backend worker; do
    wait_for_service_health "$service"
  done

  printf '%s\n' 'M8 bounded Redis outage and readiness recovery'
  compose_call stop redis
  wait_for_worker_not_ready
  compose_call start redis
  wait_for_service_health redis
  wait_for_service_health worker

  printf '%s\n' 'M8 bounded object/search outages and recovery'
  for service in minio qdrant opensearch; do
    compose_call stop "$service"
    container_id="$(compose_probe_call ps -aq "$service")"
    if [[ "$(docker_probe_call inspect --format '{{.State.Running}}' "$container_id")" != false ]]; then
      printf 'dependency did not stop: %s\n' "$service" >&2
      exit 1
    fi
    compose_call start "$service"
    wait_for_service_health "$service"
  done

  printf '%s\n' 'M8 PostgreSQL restart after G011 live-volume proof'
  compose_call restart postgres
  wait_for_service_health postgres
  database_name="$(run_with_timeout "$probe_timeout_seconds" awk -F= '$1 == "POSTGRES_DB" {print $2; exit}' "$env_file")"
  migration_revision="$backup_dir/postgres-migration-revision.txt"
  compose_call exec -T postgres psql --no-psqlrc --quiet --tuples-only --no-align \
    --set=ON_ERROR_STOP=1 --username migration --dbname "$database_name" \
    --command 'SELECT version_num FROM app.alembic_version;' \
    >"$migration_revision"
  run_with_timeout "$probe_timeout_seconds" grep -qx 0009_operational_consistency \
    "$migration_revision"
}

assert_fresh_project
cleanup_project_resources=true
run_g011_gate
run_fresh_start
run_restart_and_outages

manifest_checksum="$(run_with_timeout "$probe_timeout_seconds" sha256sum "$backup_dir/manifest.json" | cut -d' ' -f1)"
printf 'PASS: M8 production fresh/restart/outage smoke project=%s manifest_sha256=%s\n' \
  "$project" "$manifest_checksum"
