#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy-compose.sh --environment <dev|prod>

Deploys the checked-out revision with the environment file stored locally on
the target self-hosted runner. DEPLOY_ENV_FILE is an absolute runner-local
path and is never copied into the repository or printed to logs.
EOF
}

environment=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment)
      environment="${2:-}"
      shift 2
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

case "$environment" in
  dev)
    # Development is deployed as a production-style runtime with dev-only
    # namespace and secrets. The local hot-reload override is not suitable
    # for a long-running shared VM.
    compose_override="compose.prod.yml"
    project="nh-ad-dev"
    ;;
  prod)
    compose_override="compose.prod.yml"
    project="nh-ad-prod"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

env_file="${DEPLOY_ENV_FILE:-}"
[[ -n "$env_file" && "$env_file" = /* && -f "$env_file" ]] || {
  echo "DEPLOY_ENV_FILE must reference an existing absolute path on the runner." >&2
  exit 1
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

compose=(docker compose -p "$project" -f compose.yml -f "$compose_override" --env-file "$env_file")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --remove-orphans --wait --wait-timeout 240

for service in frontend backend worker postgres redis minio qdrant opensearch; do
  container_id="$("${compose[@]}" ps -q "$service")"
  [[ -n "$container_id" ]] || {
    echo "Required service was not created: $service" >&2
    exit 1
  }
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  [[ "$state" == "healthy" ]] || {
    echo "Required service is not healthy: $service" >&2
    exit 1
  }
done

echo "Compose deployment completed for $environment using project $project."
