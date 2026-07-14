#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required command not found: $command_name" >&2
    exit 1
  fi
}

require_command git
require_command python3

chmod +x \
  "$ROOT/scripts/check-doc-consistency.sh" \
  "$ROOT/scripts/manage-skill-adapters.sh" \
  "$ROOT/.githooks/pre-commit" \
  "$ROOT/.githooks/pre-push"

git config core.hooksPath .githooks
echo "configured git hooksPath: .githooks"

"$ROOT/scripts/manage-skill-adapters.sh" install

python3 -m unittest discover -s tests/governance -v
"$ROOT/scripts/check-doc-consistency.sh"
python3 -m scripts.doc_guard validate --scope all

echo "developer tools setup complete"
