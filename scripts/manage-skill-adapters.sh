#!/usr/bin/env bash
set -euo pipefail

ROOT="${SKILL_ADAPTER_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SOURCE_ROOT="$ROOT/skills"
HASH_FILE=".skill-adapter-source.sha256"
MODE="${SKILL_ADAPTER_MODE:-auto}"
ADAPTER_ROOTS=("$ROOT/.agents/skills" "$ROOT/.claude/skills")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# shellcheck source=scripts/skill-adapters/common.sh
source "$SCRIPT_DIR/skill-adapters/common.sh"
# shellcheck source=scripts/skill-adapters/operations.sh
source "$SCRIPT_DIR/skill-adapters/operations.sh"

usage() {
  echo "usage: scripts/manage-skill-adapters.sh <install|validate>" >&2
}

install_adapters() {
  local adapter_root
  local source

  case "$MODE" in
    auto|symlink|copy) ;;
    *)
      echo "invalid SKILL_ADAPTER_MODE: $MODE" >&2
      return 1
      ;;
  esac

  validate_skill_sources
  for adapter_root in "${ADAPTER_ROOTS[@]}"; do
    ensure_adapter_root "$adapter_root" "true"
    for source in "$SOURCE_ROOT"/*; do
      [ -d "$source" ] || continue
      [ -f "$source/SKILL.md" ] || continue
      install_adapter "$source" "$adapter_root"
    done
    cleanup_stale_adapters "$adapter_root"
  done
}

validate_adapters() {
  local adapter_root
  local source
  local failed=0

  validate_skill_sources
  for adapter_root in "${ADAPTER_ROOTS[@]}"; do
    if ! ensure_adapter_root "$adapter_root" "false"; then
      failed=1
      continue
    fi
    for source in "$SOURCE_ROOT"/*; do
      [ -d "$source" ] || continue
      [ -f "$source/SKILL.md" ] || continue
      if ! validate_adapter "$source" "$adapter_root"; then
        failed=1
      fi
    done
    if ! validate_no_stale_adapters "$adapter_root"; then
      failed=1
    fi
  done

  return "$failed"
}

command_name="${1:-}"
case "$command_name" in
  install)
    install_adapters
    validate_adapters
    ;;
  validate)
    validate_adapters
    ;;
  *)
    usage
    exit 2
    ;;
esac
