#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

export GITHUB_REPOSITORY="bhjeon-cginside/nh-ad-compliance"
export GITHUB_SHA="$(git rev-parse HEAD)"

dry_run_output="$(scripts/publish-notion-docs-test.sh --dry-run)"

grep -q '^selected_markdown_count=93$' <<<"$dry_run_output"
grep -q '^excluded_non_markdown_count=33$' <<<"$dry_run_output"

rendered="$(scripts/publish-notion-docs-test.sh --render docs/project-rules.md)"

grep -q '^# 프로젝트 규칙$' <<<"$(sed -n '1p' <<<"$rendered")"
grep -q 'Git `main`의 `docs/project-rules.md`에서 자동 배포된 열람용 문서' <<<"$rendered"
grep -q "github.com/$GITHUB_REPOSITORY/blob/$GITHUB_SHA/docs/adr/ADR-0031-ai-assisted-development-responsibility.md" <<<"$rendered"

if grep -q '](adr/' <<<"$rendered"; then
  echo "relative Markdown links remain after rendering" >&2
  exit 1
fi

echo "notion publish script contract passed"
