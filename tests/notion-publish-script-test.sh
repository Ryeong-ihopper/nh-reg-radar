#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

export GITHUB_REPOSITORY="CGINSIDE-ROOKIES/nh-ad-compliance"
export GITHUB_SHA="$(git rev-parse HEAD)"

workflow_path=".github/workflows/notion-docs-publish-test.yml"
job_environment="$(
  awk '
    /^    env:$/ { capture = 1; next }
    capture && /^    [^ ]/ { exit }
    capture { print }
  ' "$workflow_path"
)"
if grep -q 'NOTION_API_TOKEN' <<<"$job_environment"; then
  echo "Notion API token must not be exposed to every workflow step" >&2
  exit 1
fi
grep -q '^  push:$' "$workflow_path"
grep -q '      - dev' "$workflow_path"
grep -q 'SYNC_DEV_DOCS' "$workflow_path"
grep -q 'scripts/publish-notion-docs-test.sh --sync' "$workflow_path"

# The automatic sync source is a paired change: push trigger, run lookup branch and
# event filter must stay consistent. Assert the lookup conditions inside the single
# "Select synchronization base" step so flipping one side alone fails here.
sync_base_step="$(
  awk '/^      - name: Select synchronization base$/{flag=1} /^      - name: Install official Notion CLI$/{flag=0} flag' \
    "$workflow_path"
)"
test -n "$sync_base_step"
grep -q 'gh run list' <<<"$sync_base_step"
grep -q -- '--branch dev' <<<"$sync_base_step"
grep -q -- '--event push' <<<"$sync_base_step"
grep -q -- '--status success' <<<"$sync_base_step"
if grep -q -- '--branch main' <<<"$sync_base_step"; then
  echo "sync base lookup must not target main after the dev source flip" >&2
  exit 1
fi

checkout_step="$(
  awk '
    /^      - name: Check out repository$/ { capture = 1 }
    capture && /^      - name:/ && $0 !~ /Check out repository/ { exit }
    capture { print }
  ' "$workflow_path"
)"
if ! grep -q 'persist-credentials: false' <<<"$checkout_step"; then
  echo "checkout credentials must not persist into the runtime installer step" >&2
  exit 1
fi

dry_run_output="$(scripts/publish-notion-docs-test.sh --dry-run)"
grep -q '^selected_markdown_count=102$' <<<"$dry_run_output"
grep -q '^general_markdown_count=17$' <<<"$dry_run_output"
grep -q '^adr_markdown_count=85$' <<<"$dry_run_output"
grep -q '^excluded_markdown_count=17$' <<<"$dry_run_output"
grep -q '^excluded_non_markdown_count=33$' <<<"$dry_run_output"

manifest="$(scripts/publish-notion-docs-test.sh --manifest)"
test "$(awk -F '\t' '$1 == "general" {count++} END {print count + 0}' <<<"$manifest")" -eq 17
test "$(awk -F '\t' '$1 == "adr" {count++} END {print count + 0}' <<<"$manifest")" -eq 85
grep -q $'^general\t00\tdocs/project-rules.md\t프로젝트 규칙$' <<<"$manifest"
grep -q $'^general\t01\tdocs/requirements-definition.md\t01. 요구사항 정의서$' <<<"$manifest"
grep -q $'^general\t14\tdocs/risk-assessment-criteria.md\t14. 위험도 산정 기준표$' <<<"$manifest"
grep -q $'^general\t15\tdocs/self-hosted-runner-guide.md\t참고. CI 및 self-hosted Compose 배포 운영 가이드$' <<<"$manifest"
grep -q $'^general\t16\tdocs/architecture-overview.md\t참고. 아키텍처 구성도 모음$' <<<"$manifest"
grep -q $'^adr\t00\tdocs/adr/README.md\t00. ADR 목록$' <<<"$manifest"
grep -q $'^adr\t01\tdocs/adr/decision-questions.md\t01. ADR 의사결정 질문지$' <<<"$manifest"
grep -q $'^adr\tADR-0076\tdocs/adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md\tADR-0076: AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층$' <<<"$manifest"
grep -q $'^adr\tADR-0077\tdocs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md\tADR-0077: Git-Notion 단방향 문서 자동 동기화 정책$' <<<"$manifest"
grep -q $'^adr\tADR-0078\tdocs/adr/ADR-0078-poc-two-account-operation-profile.md\tADR-0078: PoC 2계정 운영 프로필 정책$' <<<"$manifest"
grep -q $'^adr\tADR-0079\tdocs/adr/ADR-0079-hwp-hwpx-hybrid-parser-composition.md\tADR-0079: HWP/HWPX 이중 원천 Hybrid Parser 구성 정책$' <<<"$manifest"
scripts/publish-notion-docs-test.sh --validate-map

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
sync_result_path="$ROOT/notion-sync-result.json"
cleanup() {
  rm -rf "$mock_dir"
  rm -f "$result_path" "$sync_result_path"
}
trap cleanup EXIT
mkdir -p "$mock_dir/markdown" "$mock_dir/titles" "$mock_dir/parents"
printf '0' >"$mock_dir/counter"
printf '0' >"$mock_dir/divider-counter"
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
    printf '%s' "$markdown" >"$MOCK_NTN_STATE_DIR/markdown/$page_id"
    printf '%s' "$parent" >"$MOCK_NTN_STATE_DIR/parents/$page_id"
    printf 'create\t%s\t%s\t%s\n' "$page_id" "$parent" "$first_line" >>"$event_log"
    jq -n --arg id "$page_id" --arg url "https://notion.example/$page_id" '{id:$id,url:$url}'
    ;;
  pages:update)
    page_id="$3"
    markdown="$(cat)"
    printf '%s' "$markdown" >"$MOCK_NTN_STATE_DIR/markdown/$page_id"
    printf 'update\t%s\n' "$page_id" >>"$event_log"
    jq -n --arg id "$page_id" --arg markdown "$markdown" \
      '{object:"page_markdown",id:$id,markdown:$markdown,truncated:false,unknown_block_ids:[]}'
    ;;
  pages:get)
    page_id="$3"
    if [ "${MOCK_NTN_PERMANENT_GET_PAGE:-}" = "$page_id" ]; then
      echo 'error: Public API request failed: 502 Bad Gateway' >&2
      exit 5
    fi
    if [ "${MOCK_NTN_FAIL_GET_AFTER_UPDATE_PAGE:-}" = "$page_id" ] \
      && grep -q $'^update\t'"$page_id"'$' "$event_log"; then
      echo 'error: Public API request failed: 502 Bad Gateway' >&2
      exit 5
    fi
    if [ "$page_id" = "mock-page-1" ] && [ ! -e "$MOCK_NTN_STATE_DIR/transient-get-failed" ]; then
      : >"$MOCK_NTN_STATE_DIR/transient-get-failed"
      echo 'error: Public API request failed: 502 Bad Gateway' >&2
      exit 5
    fi
    title="$(cat "$MOCK_NTN_STATE_DIR/titles/$page_id")"
    parent="$(cat "$MOCK_NTN_STATE_DIR/parents/$page_id")"
    jq -n --rawfile markdown "$MOCK_NTN_STATE_DIR/markdown/$page_id" --arg id "$page_id" --arg parent "$parent" --arg title "$title" \
      '{page:{id:$id,url:("https://notion.example/" + $id),in_trash:false,is_locked:true,parent:{page_id:$parent},properties:{title:{title:[{plain_text:$title}]}}},markdown:{truncated:false,unknown_block_ids:[],markdown:$markdown}}'
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

    if [ -z "$request" ] && [[ "$endpoint" == v1/pages/* ]]; then
      page_id="${endpoint##*/}"
      if [ -f "$MOCK_NTN_STATE_DIR/titles/$page_id" ]; then
        title="$(cat "$MOCK_NTN_STATE_DIR/titles/$page_id")"
        printf '{"id":"%s","url":"https://notion.example/%s","in_trash":false,"is_locked":true,"properties":{"title":{"title":[{"plain_text":"%s"}]}}}\n' "$page_id" "$page_id" "$title"
        exit 0
      fi
    fi

    if [ -z "$request" ] && [[ "$endpoint" == v1/blocks/*/children ]]; then
      printf '{"results":[],"has_more":false,"next_cursor":null}\n'
      exit 0
    fi

    if [ -z "$request" ] && [[ "$endpoint" == v1/blocks/mock-divider-* ]]; then
      block_id="${endpoint##*/}"
      printf 'delete-block\t%s\n' "$block_id" >>"$event_log"
      jq -n --arg id "$block_id" '{id:$id,in_trash:true}'
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
      printf '%s' "$parent" >"$MOCK_NTN_STATE_DIR/parents/$page_id"
      printf 'container\t%s\t%s\t%s\n' "$page_id" "$parent" "$title" >>"$event_log"
      jq -n --arg id "$page_id" --arg url "https://notion.example/$page_id" --arg title "$title" \
        '{id:$id,url:$url,properties:{title:{title:[{plain_text:$title}]}}}'
      exit 0
    fi

    page_id="${endpoint##*/}"
    if jq -e '.children[0].type == "divider"' <<<"$request" >/dev/null 2>&1; then
      divider_count="$(cat "$MOCK_NTN_STATE_DIR/divider-counter")"
      divider_count=$((divider_count + 1))
      printf '%s' "$divider_count" >"$MOCK_NTN_STATE_DIR/divider-counter"
      printf 'divider\t%s\n' "$(cut -d/ -f3 <<<"$endpoint")" >>"$event_log"
      jq --arg id "mock-divider-$divider_count" '.children[0].id = $id | {results:.children}' <<<"$request"
    elif jq -e '.in_trash == true' <<<"$request" >/dev/null; then
      printf 'trash\t%s\n' "$page_id" >>"$event_log"
      jq -n --arg id "$page_id" '{id:$id,in_trash:true}'
    elif jq -e 'has("is_locked")' <<<"$request" >/dev/null; then
      lock_state="$(jq -r '.is_locked' <<<"$request")"
      if [ "${MOCK_NTN_FAIL_LOCK_PAGE:-}" = "$page_id" ] && [ "$lock_state" = "true" ]; then
        echo 'error: Public API request failed: 502 Bad Gateway' >&2
        exit 5
      fi
      if [ "$lock_state" = "true" ]; then
        printf 'lock\t%s\n' "$page_id" >>"$event_log"
      else
        printf 'unlock\t%s\n' "$page_id" >>"$event_log"
      fi
      jq -n --argjson is_locked "$lock_state" '{is_locked:$is_locked}'
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
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --publish >/dev/null

jq -e '
  .root_page_id == "test-parent"
  and .adr_page_id == "mock-page-18"
  and .published_count == 102
  and .general_count == 17
  and .adr_count == 85
  and (.pages | length == 102)
  and .pages[0].display_title == "프로젝트 규칙"
  and .pages[1].display_title == "01. 요구사항 정의서"
  and .pages[14].display_title == "14. 위험도 산정 기준표"
  and .pages[15].display_title == "참고. CI 및 self-hosted Compose 배포 운영 가이드"
  and .pages[16].display_title == "참고. 아키텍처 구성도 모음"
  and .pages[17].display_title == "00. ADR 목록"
  and .pages[18].display_title == "01. ADR 의사결정 질문지"
  and .pages[-1].display_title == "ADR-0083: 개발 기간 Notion 동기화 원천 dev 확장 정책"
' "$result_path" >/dev/null

test "$(awk -F '\t' '$1 == "create" && $3 == "test-parent" {count++} END {print count + 0}' "$mock_dir/events")" -eq 17
test "$(awk -F '\t' '$1 == "create" && $3 == "mock-page-18" {count++} END {print count + 0}' "$mock_dir/events")" -eq 85
grep -q $'^container\tmock-page-18\ttest-parent\t15. ADR$' "$mock_dir/events"
if grep -q $'^create\t.*\ttest-parent\t# 15. ADR$' "$mock_dir/events"; then
  echo "ADR container contains an unnecessary heading block" >&2
  exit 1
fi
test "$(awk -F '\t' '$1 == "divider" && $2 == "test-parent" {count++} END {print count + 0}' "$mock_dir/events")" -eq 2
test "$(awk -F '\t' '$1 == "lock" {count++} END {print count + 0}' "$mock_dir/events")" -eq 104
grep -q $'^lock\ttest-parent$' "$mock_dir/events"
grep -q $'^lock\tmock-page-18$' "$mock_dir/events"

mock_map="$mock_dir/notion-page-map.json"
jq '{version:1,root_page_id,adr_page_id,last_published_commit:.commit_sha,pages:[.pages[] | {source_path,section,page_id,state:"active"}]}' \
  "$result_path" >"$mock_map"
: >"$mock_dir/events"

PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$mock_map" \
  NOTION_SYNC_PATHS=docs/project-rules.md \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null

jq -e '
  .synced_count == 1
  and .pages[0].action == "updated"
  and .pages[0].source_path == "docs/project-rules.md"
  and .pages[0].page_id == "mock-page-1"
  and .pages[0].verified == true
' "$sync_result_path" >/dev/null
test "$(awk -F '\t' '$1 == "update" && $2 == "mock-page-1" {count++} END {print count + 0}' "$mock_dir/events")" -eq 1
test "$(awk -F '\t' '$1 == "create" {count++} END {print count + 0}' "$mock_dir/events")" -eq 0
grep -q $'^unlock\tmock-page-1$' "$mock_dir/events"
grep -q $'^lock\tmock-page-1$' "$mock_dir/events"

create_map="$mock_dir/notion-page-map-create.json"
jq '(.pages[] | select(.source_path == "docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md") | .page_id) = null' \
  "$mock_map" >"$create_map"
adr_0077_page_id="$(jq -r '.pages[] | select(.source_path == "docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md") | .page_id' "$mock_map")"
rm -f "$mock_dir/markdown/$adr_0077_page_id" "$mock_dir/titles/$adr_0077_page_id" "$mock_dir/parents/$adr_0077_page_id"
rm -f "$sync_result_path"
: >"$mock_dir/events"
if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$create_map" \
  NOTION_SYNC_PATHS=docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null 2>&1; then
  echo "synchronization must reject an unmapped page unless creation is explicitly allowed" >&2
  exit 1
fi
test "$(awk -F '\t' '$1 == "create" {count++} END {print count + 0}' "$mock_dir/events")" -eq 0

: >"$mock_dir/events"
PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$create_map" \
  NOTION_SYNC_PATHS=docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md \
  NOTION_ALLOW_CREATE=1 \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null
jq -e '
  .synced_count == 1
  and .pages[0].action == "created"
  and .pages[0].source_path == "docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md"
  and .pages[0].page_id != null
' "$sync_result_path" >/dev/null
test "$(awk -F '\t' '$1 == "create" && $3 == "mock-page-18" {count++} END {print count + 0}' "$mock_dir/events")" -eq 1

# allow_create must reject multiple sync paths (one page per provisioning run)
rm -f "$sync_result_path"
: >"$mock_dir/events"
if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$create_map" \
  NOTION_SYNC_PATHS="docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md,docs/adr/ADR-0078-poc-two-account-operation-profile.md" \
  NOTION_ALLOW_CREATE=1 \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null 2>&1; then
  echo "allow_create must reject multiple sync paths" >&2
  exit 1
fi
test "$(awk -F '\t' '$1 == "create" {count++} END {print count + 0}' "$mock_dir/events")" -eq 0

# allow_create must reject an empty (non-explicit) sync selection
: >"$mock_dir/events"
if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$create_map" \
  NOTION_SYNC_BASE_SHA="$GITHUB_SHA" \
  NOTION_ALLOW_CREATE=1 \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null 2>&1; then
  echo "allow_create must reject an empty sync selection" >&2
  exit 1
fi
test "$(awk -F '\t' '$1 == "create" {count++} END {print count + 0}' "$mock_dir/events")" -eq 0

# allow_create must reject an already-mapped path (creation not needed)
: >"$mock_dir/events"
if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$create_map" \
  NOTION_SYNC_PATHS=docs/project-rules.md \
  NOTION_ALLOW_CREATE=1 \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null 2>&1; then
  echo "allow_create must reject an already-mapped path" >&2
  exit 1
fi
test "$(awk -F '\t' '$1 == "create" {count++} END {print count + 0}' "$mock_dir/events")" -eq 0
test "$(awk -F '\t' '$1 == "update" {count++} END {print count + 0}' "$mock_dir/events")" -eq 0

# created page ID must be recoverable from the result artifact even if a final container lock fails
rm -f "$sync_result_path"
: >"$mock_dir/events"
if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  MOCK_NTN_FAIL_LOCK_PAGE=test-parent \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$create_map" \
  NOTION_SYNC_PATHS=docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md \
  NOTION_ALLOW_CREATE=1 \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null 2>&1; then
  echo "synchronization must fail when a final container lock cannot be applied" >&2
  exit 1
fi
test -e "$sync_result_path"
jq -e '
  .synced_count == 1
  and .pages[0].action == "created"
  and .pages[0].source_path == "docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md"
  and .pages[0].page_id != null
' "$sync_result_path" >/dev/null

rm -f "$sync_result_path"
: >"$mock_dir/events"
if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  MOCK_NTN_FAIL_GET_AFTER_UPDATE_PAGE=mock-page-1 \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_PAGE_MAP_PATH="$mock_map" \
  NOTION_SYNC_PATHS=docs/project-rules.md \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_ATTEMPTS=2 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --sync >/dev/null 2>&1; then
  echo "synchronization must fail when updated content cannot be verified" >&2
  exit 1
fi
test ! -e "$sync_result_path"
test "$(awk -F '\t' '$1 == "update" && $2 == "mock-page-1" {count++} END {print count + 0}' "$mock_dir/events")" -eq 2
grep -q $'^lock\tmock-page-1$' "$mock_dir/events"

rm -f "$result_path" "$sync_result_path" "$mock_dir/transient-get-failed"
rm -rf "$mock_dir/markdown" "$mock_dir/titles" "$mock_dir/parents"
mkdir -p "$mock_dir/markdown" "$mock_dir/titles" "$mock_dir/parents"
printf '0' >"$mock_dir/counter"
printf '0' >"$mock_dir/divider-counter"
: >"$mock_dir/events"

if PATH="$mock_dir:$PATH" \
  MOCK_NTN_STATE_DIR="$mock_dir" \
  MOCK_NTN_PERMANENT_GET_PAGE=mock-page-19 \
  NOTION_API_TOKEN=test-token \
  NOTION_PARENT_PAGE_ID=test-parent \
  NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_ATTEMPTS=2 \
  NOTION_RETRY_DELAY_SECONDS=0 \
  scripts/publish-notion-docs-test.sh --publish >/dev/null 2>&1; then
  echo "publication must fail when Notion verification remains unavailable" >&2
  exit 1
fi

test ! -e "$result_path"
test "$(awk -F '\t' '$1 == "trash" {count++} END {print count + 0}' "$mock_dir/events")" -eq 18
grep -q $'^delete-block\tmock-divider-1$' "$mock_dir/events"
grep -q $'^delete-block\tmock-divider-2$' "$mock_dir/events"
grep -q $'^unlock\ttest-parent$' "$mock_dir/events"

echo "notion publish script contract passed"
