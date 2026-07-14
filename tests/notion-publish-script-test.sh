#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

export GITHUB_REPOSITORY="bhjeon-cginside/nh-ad-compliance"
export GITHUB_SHA="$(git rev-parse HEAD)"

dry_run_output="$(scripts/publish-notion-docs-test.sh --dry-run)"
grep -q '^selected_markdown_count=93$' <<<"$dry_run_output"
grep -q '^general_markdown_count=15$' <<<"$dry_run_output"
grep -q '^adr_markdown_count=78$' <<<"$dry_run_output"
grep -q '^excluded_non_markdown_count=33$' <<<"$dry_run_output"

manifest="$(scripts/publish-notion-docs-test.sh --manifest)"
test "$(awk -F '\t' '$1 == "general" {count++} END {print count + 0}' <<<"$manifest")" -eq 15
test "$(awk -F '\t' '$1 == "adr" {count++} END {print count + 0}' <<<"$manifest")" -eq 78
grep -q $'^general\t01\tdocs/requirements-definition.md\t01. 요구사항 정의서$' <<<"$manifest"
grep -q $'^general\t15\tdocs/risk-assessment-criteria.md\t15. 위험도 산정 기준표$' <<<"$manifest"
grep -q $'^adr\t00\tdocs/adr/README.md\t00. ADR 목록$' <<<"$manifest"
grep -q $'^adr\t01\tdocs/adr/decision-questions.md\t01. ADR 의사결정 질문지$' <<<"$manifest"
grep -q $'^adr\tADR-0076\tdocs/adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md\tADR-0076: AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층$' <<<"$manifest"

rendered="$(scripts/publish-notion-docs-test.sh --render docs/project-rules.md)"
grep -q '^# 프로젝트 규칙$' <<<"$(sed -n '1p' <<<"$rendered")"
grep -q "github.com/$GITHUB_REPOSITORY/blob/$GITHUB_SHA/docs/adr/ADR-0031-ai-assisted-development-responsibility.md" <<<"$rendered"

if grep -Eq '자동 배포된 열람용 문서|변경 요청은 Notion|^> 원본:|^> 커밋:|^> 동기화:' <<<"$rendered"; then
  echo "rendered document contains publication metadata" >&2
  exit 1
fi

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
mkdir -p "$mock_dir/titles"
printf '0' >"$mock_dir/counter"
: >"$mock_dir/events"

cat >"$mock_dir/ntn" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

event_log="$MOCK_NTN_STATE_DIR/events"

case "${1:-}:${2:-}" in
  pages:create)
    parent=""
    previous=""
    for argument in "$@"; do
      if [ "$previous" = "--parent" ]; then
        parent="${argument#page:}"
        break
      fi
      previous="$argument"
    done

    markdown="$(cat)"
    count="$(cat "$MOCK_NTN_STATE_DIR/counter")"
    count=$((count + 1))
    printf '%s' "$count" >"$MOCK_NTN_STATE_DIR/counter"
    page_id="mock-page-$count"
    first_line="$(sed -n '1p' <<<"$markdown")"
    printf 'create\t%s\t%s\t%s\n' "$page_id" "$parent" "$first_line" >>"$event_log"
    jq -n --arg id "$page_id" --arg url "https://notion.example/$page_id" '{id:$id,url:$url}'
    ;;
  pages:get)
    page_id="$3"
    title="$(cat "$MOCK_NTN_STATE_DIR/titles/$page_id")"
    probes="$(
      while IFS= read -r source_path; do
        awk '/^## / {print; exit}' "$source_path"
      done < <(git ls-files -- 'docs/*.md' 'docs/**/*.md' | LC_ALL=C sort)
    )"
    jq -n --arg probes "$probes" --arg title "$title" \
      '{page:{is_locked:true,properties:{title:{title:[{plain_text:$title}]}}},markdown:{truncated:false,unknown_block_ids:[],markdown:$probes}}'
    ;;
  pages:edit)
    echo 'pages edit must not be used for hierarchical publication' >&2
    exit 5
    ;;
  api:*)
    endpoint="$2"
    request="$(cat)"

    if [ -z "$request" ] && [ "$endpoint" = "v1/pages/test-parent" ]; then
      printf '{"url":"https://notion.example/test-parent","in_trash":false,"properties":{"title":{"title":[{"plain_text":"개발 문서"}]}}}\n'
      exit 0
    fi

    if [ -z "$request" ] && [[ "$endpoint" == v1/blocks/*/children ]]; then
      printf '{"results":[],"has_more":false,"next_cursor":null}\n'
      exit 0
    fi

    if ! jq -e . <<<"$request" >/dev/null 2>&1; then
      echo 'error: Invalid JSON from stdin' >&2
      exit 4
    fi

    if [ "$endpoint" = "v1/pages" ]; then
      count="$(cat "$MOCK_NTN_STATE_DIR/counter")"
      count=$((count + 1))
      printf '%s' "$count" >"$MOCK_NTN_STATE_DIR/counter"
      page_id="mock-page-$count"
      parent="$(jq -er '.parent.page_id' <<<"$request")"
      title="$(jq -er '.properties.title.title[0].text.content' <<<"$request")"
      printf '%s' "$title" >"$MOCK_NTN_STATE_DIR/titles/$page_id"
      printf 'container\t%s\t%s\t%s\n' "$page_id" "$parent" "$title" >>"$event_log"
      jq -n --arg id "$page_id" --arg url "https://notion.example/$page_id" --arg title "$title" \
        '{id:$id,url:$url,properties:{title:{title:[{plain_text:$title}]}}}'
      exit 0
    fi

    page_id="${endpoint##*/}"
    if jq -e '.children[0].type == "divider"' <<<"$request" >/dev/null 2>&1; then
      printf 'divider\t%s\n' "$(cut -d/ -f3 <<<"$endpoint")" >>"$event_log"
      jq '{results:.children}' <<<"$request"
    elif jq -e '.is_locked == true' <<<"$request" >/dev/null; then
      printf 'lock\t%s\n' "$page_id" >>"$event_log"
      printf '{"is_locked":true}\n'
    else
      title="$(jq -er '.properties.title.title[0].text.content' <<<"$request")"
      printf '%s' "$title" >"$MOCK_NTN_STATE_DIR/titles/$page_id"
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

jq -e '
  .root_page_id == "test-parent"
  and .adr_page_id == "mock-page-16"
  and .published_count == 93
  and .general_count == 15
  and .adr_count == 78
  and (.pages | length == 93)
  and .pages[0].display_title == "01. 요구사항 정의서"
  and .pages[14].display_title == "15. 위험도 산정 기준표"
  and .pages[15].display_title == "00. ADR 목록"
  and .pages[16].display_title == "01. ADR 의사결정 질문지"
  and .pages[-1].display_title == "ADR-0076: AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층"
' "$result_path" >/dev/null

test "$(awk -F '\t' '$1 == "create" && $3 == "test-parent" {count++} END {print count + 0}' "$mock_dir/events")" -eq 15
test "$(awk -F '\t' '$1 == "create" && $3 == "mock-page-16" {count++} END {print count + 0}' "$mock_dir/events")" -eq 78
grep -q $'^container\tmock-page-16\ttest-parent\t16. ADR$' "$mock_dir/events"
if grep -q $'^create\t.*\ttest-parent\t# 16. ADR$' "$mock_dir/events"; then
  echo "ADR container contains an unnecessary heading block" >&2
  exit 1
fi
test "$(awk -F '\t' '$1 == "divider" && $2 == "test-parent" {count++} END {print count + 0}' "$mock_dir/events")" -eq 1
test "$(awk -F '\t' '$1 == "lock" {count++} END {print count + 0}' "$mock_dir/events")" -eq 95
grep -q $'^lock\ttest-parent$' "$mock_dir/events"
grep -q $'^lock\tmock-page-16$' "$mock_dir/events"

echo "notion publish script contract passed"
