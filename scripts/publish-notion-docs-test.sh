#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

MODE="${1:---publish}"
REPOSITORY="${GITHUB_REPOSITORY:-bhjeon-cginside/nh-ad-compliance}"
COMMIT_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
SYNCED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
EXPECTED_MARKDOWN_COUNT="${EXPECTED_MARKDOWN_COUNT:-93}"
REQUEST_INTERVAL_SECONDS="${NOTION_REQUEST_INTERVAL_SECONDS:-0.4}"

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required command not found: $command_name" >&2
    exit 1
  fi
}

list_markdown_files() {
  git ls-files -- 'docs/*.md' 'docs/**/*.md' | LC_ALL=C sort
}

count_non_markdown_files() {
  git ls-files docs | awk '!/\.md$/ { count += 1 } END { print count + 0 }'
}

render_markdown() {
  local source_path="$1"
  local source_dir
  local source_url

  source_dir="$(dirname "$source_path")"
  source_url="https://github.com/$REPOSITORY/blob/$COMMIT_SHA/$source_path"

  SOURCE_PATH="$source_path" \
    SOURCE_DIR="$source_dir" \
    SOURCE_URL="$source_url" \
    REPOSITORY="$REPOSITORY" \
    COMMIT_SHA="$COMMIT_SHA" \
    SYNCED_AT="$SYNCED_AT" \
    perl -0777 -pe '
      s{\A(# [^\n]+\n)}{$1 . "\n> Git `main`의 `$ENV{SOURCE_PATH}`에서 자동 배포된 열람용 문서입니다. 변경 요청은 Notion 페이지 댓글로 남기고, 원문 변경은 Git PR로 반영합니다.\n>\n> 원본: $ENV{SOURCE_URL}  \n> 커밋: `$ENV{COMMIT_SHA}`  \n> 동기화: $ENV{SYNCED_AT}\n\n"}e;
      s{\]\((?!https?://|mailto:|#)([^)#]+\.md)(#[^)]+)?\)}{
        my $link = $1;
        my $anchor = defined($2) ? $2 : "";
        my $target = "$ENV{SOURCE_DIR}/$link";
        $target =~ s{/\./}{/}g;
        "](https://github.com/$ENV{REPOSITORY}/blob/$ENV{COMMIT_SHA}/$target$anchor)";
      }ge;
    ' "$source_path"
}

validate_selection() {
  local selected_count
  local source_path
  local title

  selected_count="$(list_markdown_files | wc -l | tr -d ' ')"
  if [ "$selected_count" -ne "$EXPECTED_MARKDOWN_COUNT" ]; then
    echo "expected $EXPECTED_MARKDOWN_COUNT Markdown files, found $selected_count" >&2
    exit 1
  fi

  while IFS= read -r source_path; do
    title="$(sed -n '1p' "$source_path")"
    case "$title" in
      '# '*) ;;
      *)
        echo "first line must be a level-one title: $source_path" >&2
        exit 1
        ;;
    esac
  done < <(list_markdown_files)

  printf 'selected_markdown_count=%s\n' "$selected_count"
  printf 'excluded_non_markdown_count=%s\n' "$(count_non_markdown_files)"
}

throttle() {
  sleep "$REQUEST_INTERVAL_SECONDS"
}

lock_page() {
  local page_id="$1"

  ntn api "v1/pages/$page_id" -X PATCH is_locked:=true \
    | jq -e '.is_locked == true' >/dev/null
  throttle
}

publish_documents() {
  local result_jsonl
  local root_markdown
  local temp_dir
  local root_response
  local root_page_id
  local root_page_url
  local source_path
  local page_response
  local page_id
  local page_url
  local verification
  local source_hash
  local index=0
  local selected_count
  local test_label

  require_command jq
  require_command ntn
  require_command perl
  require_command shasum

  : "${NOTION_API_TOKEN:?NOTION_API_TOKEN is required}"
  : "${NOTION_PARENT_PAGE_ID:?NOTION_PARENT_PAGE_ID is required}"

  selected_count="$(list_markdown_files | wc -l | tr -d ' ')"
  test_label="${GITHUB_RUN_ID:-local}-$(printf '%.8s' "$COMMIT_SHA")"
  temp_dir="$(mktemp -d)"
  result_jsonl="$temp_dir/results.jsonl"
  root_markdown="$temp_dir/root.md"
  trap "rm -rf '$temp_dir'" EXIT

  printf '# Git Docs Sync Test %s\n\n' "$test_label" >"$root_markdown"
  printf 'Git `docs/**/*.md` 단방향 게시 테스트입니다.\n\n' >>"$root_markdown"
  printf -- '- 대상 커밋: `%s`\n- Markdown: %s개\n- 제외: HWP/PDF/PNG/YAML 등 비 Markdown 파일\n' \
    "$COMMIT_SHA" "$selected_count" >>"$root_markdown"

  root_response="$(ntn pages create --parent "page:$NOTION_PARENT_PAGE_ID" --json <"$root_markdown")"
  root_page_id="$(jq -er '.id' <<<"$root_response")"
  root_page_url="$(jq -er '.url' <<<"$root_response")"
  throttle

  while IFS= read -r source_path; do
    index=$((index + 1))
    echo "[$index/$selected_count] publishing $source_path"

    page_response="$(render_markdown "$source_path" \
      | ntn pages create --parent "page:$root_page_id" --json)"
    page_id="$(jq -er '.id' <<<"$page_response")"
    page_url="$(jq -er '.url' <<<"$page_response")"
    throttle

    lock_page "$page_id"
    verification="$(ntn pages get "$page_id" --json)"
    throttle

    jq -e \
      --arg source_path "$source_path" \
      --arg commit_sha "$COMMIT_SHA" \
      '.page.is_locked == true
        and .markdown.truncated == false
        and (.markdown.unknown_block_ids | length == 0)
        and (.markdown.markdown | contains($source_path))
        and (.markdown.markdown | contains($commit_sha))' \
      <<<"$verification" >/dev/null

    source_hash="$(shasum -a 256 "$source_path" | awk '{print $1}')"
    jq -cn \
      --arg source_path "$source_path" \
      --arg source_sha256 "$source_hash" \
      --arg page_id "$page_id" \
      --arg page_url "$page_url" \
      '{source_path:$source_path,source_sha256:$source_sha256,page_id:$page_id,page_url:$page_url,is_locked:true}' \
      >>"$result_jsonl"
  done < <(list_markdown_files)

  {
    printf '# Git Docs Sync Test %s\n\n' "$test_label"
    printf '게시와 검증이 완료되었습니다.\n\n'
    printf -- '- 대상 커밋: `%s`\n- 게시 완료: %s개\n- 검증: 잠금, 원본 경로, 커밋, 콘텐츠 비절단\n\n' \
      "$COMMIT_SHA" "$selected_count"
    jq -r '"- [" + .source_path + "](" + .page_url + ")"' "$result_jsonl"
  } >"$root_markdown"

  ntn pages edit "$root_page_id" --json <"$root_markdown" >/dev/null
  throttle
  lock_page "$root_page_id"

  jq -s \
    --arg root_page_id "$root_page_id" \
    --arg root_page_url "$root_page_url" \
    --arg commit_sha "$COMMIT_SHA" \
    '{root_page_id:$root_page_id,root_page_url:$root_page_url,commit_sha:$commit_sha,published_count:length,pages:.}' \
    "$result_jsonl" >notion-publish-test-result.json

  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'root_page_url=%s\n' "$root_page_url" >>"$GITHUB_OUTPUT"
    printf 'published_count=%s\n' "$selected_count" >>"$GITHUB_OUTPUT"
  fi

  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      printf '## Notion 문서 게시 테스트\n\n'
      printf -- '- 루트 페이지: [%s](%s)\n' "$test_label" "$root_page_url"
      printf -- '- 게시 및 검증: %s개\n' "$selected_count"
      printf -- '- 제외: 비 Markdown 파일 %s개\n' "$(count_non_markdown_files)"
    } >>"$GITHUB_STEP_SUMMARY"
  fi

  printf 'root_page_url=%s\n' "$root_page_url"
  printf 'published_count=%s\n' "$selected_count"

  rm -rf "$temp_dir"
  trap - EXIT
}

require_command git

case "$MODE" in
  --dry-run)
    validate_selection
    ;;
  --render)
    if [ "$#" -ne 2 ] || [ ! -f "$2" ]; then
      echo "usage: $0 --render <docs/file.md>" >&2
      exit 1
    fi
    render_markdown "$2"
    ;;
  --publish)
    validate_selection
    publish_documents
    ;;
  *)
    echo "usage: $0 [--dry-run | --render <docs/file.md> | --publish]" >&2
    exit 1
    ;;
esac
