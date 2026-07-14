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

mock_dir="$(mktemp -d)"
result_path="$ROOT/notion-publish-test-result.json"
cleanup() {
  rm -rf "$mock_dir"
  rm -f "$result_path"
}
trap cleanup EXIT

cat >"$mock_dir/ntn" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}:${2:-}" in
  pages:create)
    cat >/dev/null
    printf '{"id":"mock-page-id","url":"https://notion.example/mock-page-id"}\n'
    ;;
  pages:edit)
    cat >/dev/null
    echo 'error: replacing root content would delete child pages' >&2
    exit 5
    ;;
  pages:get)
    markdown="$(git ls-files -- 'docs/*.md' 'docs/**/*.md'; printf '%s\n' "$GITHUB_SHA")"
    title="$(cat "$MOCK_NTN_STATE_DIR/title")"
    jq -n --arg markdown "$markdown" --arg title "$title" \
      '{page:{is_locked:true,properties:{title:{title:[{plain_text:$title}]}}},markdown:{truncated:false,unknown_block_ids:[],markdown:$markdown}}'
    ;;
  api:*)
    request="$(cat)"
    if ! jq -e . <<<"$request" >/dev/null 2>&1; then
      echo 'error: Invalid JSON from stdin' >&2
      exit 4
    fi

    if jq -e '.children | type == "array"' <<<"$request" >/dev/null; then
      jq '{results:.children}' <<<"$request"
    elif jq -e '.is_locked == true' <<<"$request" >/dev/null; then
      printf '{"is_locked":true}\n'
    else
      title="$(jq -er '.properties.title.title[0].text.content' <<<"$request")"
      printf '%s' "$title" >"$MOCK_NTN_STATE_DIR/title"
      jq -n --arg title "$title" \
        '{properties:{title:{title:[{plain_text:$title}]}}}'
    fi
    ;;
  *)
    echo "unsupported mock ntn command: $*" >&2
    exit 2
    ;;
esac
EOF
chmod +x "$mock_dir/ntn"

PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --publish >/dev/null

jq -e '.published_count == 93 and (.pages | length == 93)' "$result_path" >/dev/null

echo "notion publish script contract passed"
