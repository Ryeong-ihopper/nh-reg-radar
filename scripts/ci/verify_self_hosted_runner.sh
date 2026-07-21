#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/ci/verify_self_hosted_runner.sh [--deployment]

Validates the host capabilities required by the self-hosted GitHub Actions
runner. It never prints environment-file contents or credentials.
EOF
}

deployment=false
if [[ "${1:-}" == "--deployment" ]]; then
  deployment=true
elif [[ $# -ne 0 ]]; then
  usage >&2
  exit 2
fi

for command in bash git docker timeout; do
  command -v "$command" >/dev/null || {
    echo "Missing required command: $command" >&2
    exit 1
  }
done

docker version --format '{{.Server.Version}}' >/dev/null
docker compose version >/dev/null

if [[ "$deployment" == true ]]; then
  [[ -n "${DEPLOY_ENV_FILE:-}" ]] || {
    echo "DEPLOY_ENV_FILE repository/environment variable is required for deployment." >&2
    exit 1
  }
  [[ "$DEPLOY_ENV_FILE" = /* && -f "$DEPLOY_ENV_FILE" ]] || {
    echo "DEPLOY_ENV_FILE must reference an existing absolute path on the runner." >&2
    exit 1
  }
fi
