#!/usr/bin/env bash
set -euo pipefail

# Release-based SSH deploy for the shared development VM.
#
# A shared org runner (labels: self-hosted, linux, x64, org-cg-rookies, org-deploy)
# checks out the target revision, then this script rsyncs that tree to a per-commit
# release directory on DEPLOY_HOST, runs the production-runtime Compose stack from it,
# and atomically swaps the `app` symlink only after the stack reports healthy.
#
# Layout on the target host (already established):
#   $DEPLOY_PATH/app                 -> releases/<sha>   (current release symlink)
#   $DEPLOY_PATH/releases/<sha>/     (repo checkout per release)
#   $DEPLOY_PATH/env/.env.dev        (shared env file, 0600, outside the checkout)
#
# Required environment:
#   DEPLOY_HOST DEPLOY_USER DEPLOY_PATH DEPLOY_SHA
# Optional:
#   DEPLOY_PORT (default 22), COMPOSE_PROJECT (default nh-ad-dev),
#   KEEP_RELEASES (default 5)
#
# The SSH private key must already be loaded into an ssh-agent by the caller.

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-nh-ad-dev}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"

case "$DEPLOY_PATH" in
  /*) ;;
  *) echo "DEPLOY_PATH must be an absolute path: $DEPLOY_PATH" >&2; exit 1 ;;
esac
case "$DEPLOY_SHA" in
  *[!0-9a-f]*|"") echo "DEPLOY_SHA must be a hex commit sha: $DEPLOY_SHA" >&2; exit 1 ;;
esac

remote="$DEPLOY_USER@$DEPLOY_HOST"
ssh_opts=(-p "$DEPLOY_PORT" -o StrictHostKeyChecking=accept-new -o BatchMode=yes)
release_dir="$DEPLOY_PATH/releases/$DEPLOY_SHA"
env_file="$DEPLOY_PATH/env/.env.dev"
compose=(docker compose -p "$COMPOSE_PROJECT" -f compose.yml -f compose.prod.yml --env-file "$env_file")

run_remote() {
  ssh "${ssh_opts[@]}" "$remote" "$@"
}

echo "==> Preconditions on $DEPLOY_HOST"
run_remote "set -eu
  command -v docker >/dev/null || { echo 'docker missing on target' >&2; exit 1; }
  docker compose version >/dev/null || { echo 'docker compose plugin missing' >&2; exit 1; }
  test -f '$env_file' || { echo 'shared env file missing: $env_file' >&2; exit 1; }
  mkdir -p '$DEPLOY_PATH/releases' '$release_dir'"

echo "==> Syncing revision $DEPLOY_SHA to $release_dir"
rsync -az --delete \
  -e "ssh -p $DEPLOY_PORT -o StrictHostKeyChecking=accept-new -o BatchMode=yes" \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  --exclude '.pytest_cache' \
  --exclude '.omx' \
  ./ "$remote:$release_dir/"

echo "==> Building and starting the stack (health-gated)"
if ! run_remote "set -eu
  cd '$release_dir'
  ${compose[*]} build
  ${compose[*]} up -d --remove-orphans --wait --wait-timeout 600"; then
  echo "!! Deploy failed; attempting to restore the previous release" >&2
  run_remote "set -eu
    if [ -d '$DEPLOY_PATH/app' ]; then
      cd '$DEPLOY_PATH/app'
      ${compose[*]} up -d --remove-orphans --wait --wait-timeout 600 || true
    fi" || true
  exit 1
fi

echo "==> Promoting release (atomic symlink swap)"
run_remote "set -eu
  ln -sfn 'releases/$DEPLOY_SHA' '$DEPLOY_PATH/.app.new'
  mv -Tf '$DEPLOY_PATH/.app.new' '$DEPLOY_PATH/app'"

echo "==> Pruning old releases (keeping newest $KEEP_RELEASES)"
run_remote "set -eu
  cd '$DEPLOY_PATH/releases'
  current=\$(readlink -f '$DEPLOY_PATH/app' | xargs -r basename)
  ls -1dt */ 2>/dev/null | sed 's:/*\$::' | tail -n +$((KEEP_RELEASES + 1)) | while read -r old; do
    [ \"\$old\" = \"\$current\" ] && continue
    rm -rf -- \"\$old\"
  done" || true

echo "==> Deployed $DEPLOY_SHA to $COMPOSE_PROJECT on $DEPLOY_HOST"
