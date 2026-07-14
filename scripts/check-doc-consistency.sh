#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

failures=0

decode_url_path() {
  local value="$1"
  printf '%b' "${value//%/\\x}"
}

echo "[docs] checking Markdown internal links"

while IFS=$'\t' read -r file link; do
  decoded_link="$(decode_url_path "$link")"

  case "$link" in
    http://*|https://*|mailto:*|"")
      continue
      ;;
    /*)
      target="$decoded_link"
      ;;
    *)
      target="$(dirname "$file")/$decoded_link"
      ;;
  esac

  if [ ! -f "$target" ]; then
    echo "BROKEN_LINK $file -> $link"
    failures=1
  fi
done < <(
  python3 -m scripts.doc_guard files \
    | xargs -0 perl -ne 'while (/\]\(([^)#][^)]+\.md)\)/g) { print "$ARGV\t$1\n" }'
)

if [ -f "docs/api-specification.md" ]; then
  echo "[docs] checking JSON code blocks in docs/api-specification.md"
  if ! python3 - <<'PY'
import json
import re
from pathlib import Path

path = Path("docs/api-specification.md")
blocks = re.findall(r"```json\n(.*?)```", path.read_text(encoding="utf-8"), re.DOTALL)
errors = []

for index, block in enumerate(blocks, start=1):
    try:
        json.loads(block)
    except json.JSONDecodeError as error:
        errors.append(f"JSON_BLOCK {index}: {error.msg} at line {error.lineno}")

if errors:
    print("\n".join(errors))
    raise SystemExit(1)

print(f"[docs] json code blocks ok: {len(blocks)}")
PY
  then
    failures=1
  fi
fi

if [ -f "openapi/openapi.yaml" ]; then
  if command -v spectral >/dev/null 2>&1; then
    echo "[docs] checking OpenAPI with spectral"
    spectral lint openapi/openapi.yaml || failures=1
  elif [ -x "node_modules/.bin/spectral" ]; then
    echo "[docs] checking OpenAPI with local spectral"
    node_modules/.bin/spectral lint openapi/openapi.yaml || failures=1
  else
    echo "[docs] spectral not found; skipping OpenAPI lint"
  fi
fi

if [ "$failures" -ne 0 ]; then
  echo "[docs] consistency check failed"
  exit 1
fi

echo "[docs] consistency check passed"
