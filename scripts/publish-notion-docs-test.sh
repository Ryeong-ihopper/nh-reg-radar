#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

MODE="${1:---publish}"
REPOSITORY="${GITHUB_REPOSITORY:-bhjeon-cginside/nh-ad-compliance}"
COMMIT_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
EXPECTED_MARKDOWN_COUNT="${EXPECTED_MARKDOWN_COUNT:-93}"
EXPECTED_GENERAL_COUNT="${EXPECTED_GENERAL_COUNT:-15}"
EXPECTED_ADR_COUNT="${EXPECTED_ADR_COUNT:-78}"
EXPECTED_PARENT_TITLE="${EXPECTED_NOTION_PARENT_TITLE:-개발 문서}"
REQUEST_INTERVAL_SECONDS="${NOTION_REQUEST_INTERVAL_SECONDS:-0.4}"
RETRY_ATTEMPTS="${NOTION_RETRY_ATTEMPTS:-5}"
RETRY_DELAY_SECONDS="${NOTION_RETRY_DELAY_SECONDS:-2}"

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

list_general_files() {
  printf '%s\n' \
    docs/requirements-definition.md \
    docs/functional-specification.md \
    docs/screen-specification.md \
    docs/screen-api-mapping.md \
    docs/api-specification.md \
    docs/api-contract-sync-policy.md \
    docs/database-specification.md \
    docs/test-cases.md \
    docs/project-rules.md \
    docs/adr-candidates.md \
    docs/development-schedule-and-notion-kanban.md \
    docs/reference-repositories.md \
    docs/poc-kpi-formulas.md \
    docs/poc-evaluation-exclusion-criteria.md \
    docs/risk-assessment-criteria.md
}

list_adr_files() {
  printf '%s\n' docs/adr/README.md docs/adr/decision-questions.md
  git ls-files -- 'docs/adr/ADR-*.md' | LC_ALL=C sort
}

count_non_markdown_files() {
  git ls-files docs | awk '!/\.md$/ { count += 1 } END { print count + 0 }'
}

source_title() {
  sed -n '1s/^# //p' "$1"
}

content_probe() {
  awk '/^## / {print; exit}' "$1"
}

adr_order() {
  local source_path="$1"

  case "$source_path" in
    docs/adr/README.md) printf '00\n' ;;
    docs/adr/decision-questions.md) printf '01\n' ;;
    *) basename "$source_path" | sed -E 's/^(ADR-[0-9]{4}).*/\1/' ;;
  esac
}

display_title() {
  local section="$1"
  local order="$2"
  local source_path="$3"
  local title

  title="$(source_title "$source_path")"
  if [ "$section" = "general" ] || [ "$order" = "00" ] || [ "$order" = "01" ]; then
    printf '%s. %s\n' "$order" "$title"
  else
    printf '%s\n' "$title"
  fi
}

print_manifest() {
  local source_path
  local order=0
  local order_label

  while IFS= read -r source_path; do
    order=$((order + 1))
    order_label="$(printf '%02d' "$order")"
    printf 'general\t%s\t%s\t%s\n' \
      "$order_label" "$source_path" "$(display_title general "$order_label" "$source_path")"
  done < <(list_general_files)

  while IFS= read -r source_path; do
    order_label="$(adr_order "$source_path")"
    printf 'adr\t%s\t%s\t%s\n' \
      "$order_label" "$source_path" "$(display_title adr "$order_label" "$source_path")"
  done < <(list_adr_files)
}

render_markdown() {
  local source_path="$1"
  local source_dir

  source_dir="$(dirname "$source_path")"

  SOURCE_DIR="$source_dir" \
    REPOSITORY="$REPOSITORY" \
    COMMIT_SHA="$COMMIT_SHA" \
    perl -0777 -pe '
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
  local general_count
  local adr_count
  local source_path
  local title

  selected_count="$(list_markdown_files | wc -l | tr -d ' ')"
  general_count="$(list_general_files | wc -l | tr -d ' ')"
  adr_count="$(list_adr_files | wc -l | tr -d ' ')"

  if [ "$selected_count" -ne "$EXPECTED_MARKDOWN_COUNT" ]; then
    echo "expected $EXPECTED_MARKDOWN_COUNT Markdown files, found $selected_count" >&2
    exit 1
  fi
  if [ "$general_count" -ne "$EXPECTED_GENERAL_COUNT" ]; then
    echo "expected $EXPECTED_GENERAL_COUNT general documents, found $general_count" >&2
    exit 1
  fi
  if [ "$adr_count" -ne "$EXPECTED_ADR_COUNT" ]; then
    echo "expected $EXPECTED_ADR_COUNT ADR documents, found $adr_count" >&2
    exit 1
  fi
  if ! diff -u \
    <(list_markdown_files) \
    <(printf '%s\n' "$(list_general_files)" "$(list_adr_files)" | LC_ALL=C sort) >/dev/null; then
    echo "publication manifest does not cover the tracked Markdown set" >&2
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
    if [ -z "$(content_probe "$source_path")" ]; then
      echo "document must contain a level-two section for publication verification: $source_path" >&2
      exit 1
    fi
  done < <(list_markdown_files)

  printf 'selected_markdown_count=%s\n' "$selected_count"
  printf 'general_markdown_count=%s\n' "$general_count"
  printf 'adr_markdown_count=%s\n' "$adr_count"
  printf 'excluded_non_markdown_count=%s\n' "$(count_non_markdown_files)"
}

throttle() {
  sleep "$REQUEST_INTERVAL_SECONDS"
}

retry_ntn() {
  local attempt=1
  local delay="$RETRY_DELAY_SECONDS"
  local status=0
  local retry_dir

  retry_dir="$(mktemp -d)"
  cat >"$retry_dir/stdin"

  while [ "$attempt" -le "$RETRY_ATTEMPTS" ]; do
    if ntn "$@" <"$retry_dir/stdin" >"$retry_dir/stdout" 2>"$retry_dir/stderr"; then
      cat "$retry_dir/stdout"
      rm -rf "$retry_dir"
      return 0
    else
      status=$?
    fi

    if [ "$attempt" -eq "$RETRY_ATTEMPTS" ]; then
      cat "$retry_dir/stderr" >&2
      rm -rf "$retry_dir"
      return "$status"
    fi

    echo "Notion API request failed; retrying idempotent request ($attempt/$RETRY_ATTEMPTS)" >&2
    sleep "$delay"
    delay=$((delay * 2))
    attempt=$((attempt + 1))
  done
}

cleanup_publication() {
  local status="$1"
  local temp_dir="$2"
  local page_id
  local block_id

  if [ "$status" -ne 0 ]; then
    echo "Publication failed; removing pages created by this run" >&2

    if ! jq -n '{is_locked:false}' \
      | retry_ntn api "v1/pages/$NOTION_PARENT_PAGE_ID" -X PATCH --data @- \
      | jq -e '.is_locked == false' >/dev/null; then
      echo "warning: failed to unlock target page before cleanup" >&2
    fi
    throttle

    if [ -s "$temp_dir/root-page-ids" ]; then
      while IFS= read -r page_id; do
        if ! jq -n '{in_trash:true}' \
          | retry_ntn api "v1/pages/$page_id" -X PATCH --data @- \
          | jq -e --arg id "$page_id" '.id == $id and .in_trash == true' >/dev/null; then
          echo "warning: failed to remove created page $page_id" >&2
        fi
        throttle
      done < <(awk '{lines[NR]=$0} END {for (line=NR; line>0; line--) print lines[line]}' "$temp_dir/root-page-ids")
    fi

    if [ -s "$temp_dir/divider-ids" ]; then
      while IFS= read -r block_id; do
        if ! ntn api "v1/blocks/$block_id" -X DELETE </dev/null \
          | jq -e --arg id "$block_id" '.id == $id and .in_trash == true' >/dev/null; then
          echo "warning: failed to remove created divider $block_id" >&2
        fi
        throttle
      done <"$temp_dir/divider-ids"
    fi
  fi

  rm -rf "$temp_dir"
}

lock_page() {
  local page_id="$1"

  jq -n '{is_locked:true}' \
    | retry_ntn api "v1/pages/$page_id" -X PATCH --data @- \
    | jq -e '.is_locked == true' >/dev/null
  throttle
}

set_page_title() {
  local page_id="$1"
  local title="$2"

  jq -n --arg title "$title" \
    '{properties:{title:{type:"title",title:[{type:"text",text:{content:$title}}]}}}' \
    | retry_ntn api "v1/pages/$page_id" -X PATCH --data @- \
    | jq -e --arg title "$title" \
      '.properties.title.title[0].plain_text == $title' >/dev/null
  throttle
}

append_divider() {
  local parent_page_id="$1"
  local response

  response="$(
    jq -n '{children:[{object:"block",type:"divider",divider:{}}]}' \
      | ntn api "v1/blocks/$parent_page_id/children" -X PATCH --data @-
  )"
  jq -e '.results | length == 1 and .[0].type == "divider" and .[0].id != null' \
    <<<"$response" >/dev/null
  throttle
  jq -er '.results[0].id' <<<"$response"
}

validate_empty_parent() {
  local parent_page_id="$1"
  local page_response
  local children_response

  page_response="$(retry_ntn api "v1/pages/$parent_page_id" </dev/null)"
  jq -e --arg title "$EXPECTED_PARENT_TITLE" \
    '(.properties.title.title[0].plain_text // "") == $title and .in_trash == false' \
    <<<"$page_response" >/dev/null

  children_response="$(retry_ntn api "v1/blocks/$parent_page_id/children" page_size==100 </dev/null)"
  jq -e '.has_more == false and (.results | length) == 0' <<<"$children_response" >/dev/null
  jq -er '.url' <<<"$page_response"
}

create_container_page() {
  local parent_page_id="$1"
  local title="$2"
  local response

  response="$(
    jq -n --arg parent_page_id "$parent_page_id" --arg title "$title" \
      '{parent:{type:"page_id",page_id:$parent_page_id},properties:{title:{type:"title",title:[{type:"text",text:{content:$title}}]}}}' \
      | ntn api v1/pages -X POST --data @-
  )"
  jq -e --arg title "$title" \
    '.id != null and .url != null and .properties.title.title[0].plain_text == $title' \
    <<<"$response" >/dev/null
  printf '%s\n' "$response"
}

publish_document() {
  local section="$1"
  local order="$2"
  local source_path="$3"
  local title="$4"
  local parent_page_id="$5"
  local result_jsonl="$6"
  local cleanup_page_ids="${7:-}"
  local page_response
  local page_id
  local page_url
  local verification
  local content_probe
  local source_hash

  echo "publishing [$section/$order] $source_path"
  page_response="$(render_markdown "$source_path" \
    | ntn pages create --parent "page:$parent_page_id" --json)"
  page_id="$(jq -er '.id' <<<"$page_response")"
  if [ -n "$cleanup_page_ids" ]; then
    printf '%s\n' "$page_id" >>"$cleanup_page_ids"
  fi
  page_url="$(jq -er '.url' <<<"$page_response")"
  throttle

  set_page_title "$page_id" "$title"
  lock_page "$page_id"
  verification="$(retry_ntn pages get "$page_id" --json </dev/null)"
  throttle

  content_probe="$(content_probe "$source_path")"
  if ! jq -e \
    --arg title "$title" \
    --arg content_probe "$content_probe" \
    '.page.is_locked == true
      and .page.properties.title.title[0].plain_text == $title
      and .markdown.truncated == false
      and (.markdown.unknown_block_ids | length == 0)
      and (.markdown.markdown | contains($content_probe))' \
    <<<"$verification" >/dev/null; then
    echo "Notion publication verification failed: $source_path" >&2
    jq -r --arg title "$title" --arg content_probe "$content_probe" \
      '"expected_title=\($title)",
       "actual_title=\(.page.properties.title.title[0].plain_text // "")",
       "is_locked=\(.page.is_locked // false)",
       "truncated=\(.markdown.truncated // true)",
       "unknown_block_count=\((.markdown.unknown_block_ids // []) | length)",
       "content_probe=\($content_probe)",
       "content_probe_found=\((.markdown.markdown // "") | contains($content_probe))"' \
      <<<"$verification" >&2
    exit 1
  fi

  source_hash="$(shasum -a 256 "$source_path" | awk '{print $1}')"
  jq -cn \
    --arg section "$section" \
    --arg order "$order" \
    --arg source_path "$source_path" \
    --arg display_title "$title" \
    --arg source_sha256 "$source_hash" \
    --arg page_id "$page_id" \
    --arg page_url "$page_url" \
    '{section:$section,order:$order,source_path:$source_path,display_title:$display_title,source_sha256:$source_sha256,page_id:$page_id,page_url:$page_url,is_locked:true}' \
    >>"$result_jsonl"
}

publish_documents() {
  local temp_dir
  local result_jsonl
  local cleanup_page_ids
  local cleanup_divider_ids
  local root_page_url
  local adr_response
  local adr_page_id
  local adr_page_url
  local section
  local order
  local source_path
  local title
  local published_count

  require_command jq
  require_command ntn
  require_command perl
  require_command shasum

  : "${NOTION_API_TOKEN:?NOTION_API_TOKEN is required}"
  : "${NOTION_PARENT_PAGE_ID:?NOTION_PARENT_PAGE_ID is required}"

  root_page_url="$(validate_empty_parent "$NOTION_PARENT_PAGE_ID")"
  temp_dir="$(mktemp -d)"
  result_jsonl="$temp_dir/results.jsonl"
  cleanup_page_ids="$temp_dir/root-page-ids"
  cleanup_divider_ids="$temp_dir/divider-ids"
  : >"$cleanup_page_ids"
  : >"$cleanup_divider_ids"
  trap "cleanup_publication \"\$?\" \"$temp_dir\"" EXIT

  while IFS=$'\t' read -r section order source_path title; do
    publish_document "$section" "$order" "$source_path" "$title" \
      "$NOTION_PARENT_PAGE_ID" "$result_jsonl" "$cleanup_page_ids"
  done < <(print_manifest | awk -F '\t' '$1 == "general"')

  append_divider "$NOTION_PARENT_PAGE_ID" >>"$cleanup_divider_ids"
  adr_response="$(create_container_page "$NOTION_PARENT_PAGE_ID" '16. ADR')"
  adr_page_id="$(jq -er '.id' <<<"$adr_response")"
  printf '%s\n' "$adr_page_id" >>"$cleanup_page_ids"
  adr_page_url="$(jq -er '.url' <<<"$adr_response")"
  throttle

  while IFS=$'\t' read -r section order source_path title; do
    publish_document "$section" "$order" "$source_path" "$title" \
      "$adr_page_id" "$result_jsonl"
  done < <(print_manifest | awk -F '\t' '$1 == "adr"')

  lock_page "$adr_page_id"
  lock_page "$NOTION_PARENT_PAGE_ID"

  jq -s \
    --arg root_page_id "$NOTION_PARENT_PAGE_ID" \
    --arg root_page_url "$root_page_url" \
    --arg adr_page_id "$adr_page_id" \
    --arg adr_page_url "$adr_page_url" \
    --arg commit_sha "$COMMIT_SHA" \
    --argjson general_count "$EXPECTED_GENERAL_COUNT" \
    --argjson adr_count "$EXPECTED_ADR_COUNT" \
    '{root_page_id:$root_page_id,root_page_url:$root_page_url,adr_page_id:$adr_page_id,adr_page_url:$adr_page_url,commit_sha:$commit_sha,published_count:length,general_count:$general_count,adr_count:$adr_count,pages:.}' \
    "$result_jsonl" >notion-publish-test-result.json

  published_count="$(jq -r '.published_count' notion-publish-test-result.json)"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'root_page_url=%s\n' "$root_page_url" >>"$GITHUB_OUTPUT"
    printf 'adr_page_url=%s\n' "$adr_page_url" >>"$GITHUB_OUTPUT"
    printf 'published_count=%s\n' "$published_count" >>"$GITHUB_OUTPUT"
  fi

  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      printf '## Notion 개발 문서 게시 테스트\n\n'
      printf -- '- 개발 문서: [%s](%s)\n' "$EXPECTED_PARENT_TITLE" "$root_page_url"
      printf -- '- 일반 문서: %s개\n' "$EXPECTED_GENERAL_COUNT"
      printf -- '- ADR 문서: %s개\n' "$EXPECTED_ADR_COUNT"
      printf -- '- 제외: 비 Markdown 파일 %s개\n' "$(count_non_markdown_files)"
    } >>"$GITHUB_STEP_SUMMARY"
  fi

  printf 'root_page_url=%s\n' "$root_page_url"
  printf 'adr_page_url=%s\n' "$adr_page_url"
  printf 'published_count=%s\n' "$published_count"

  rm -rf "$temp_dir"
  trap - EXIT
}

require_command git

case "$MODE" in
  --dry-run)
    validate_selection
    ;;
  --manifest)
    validate_selection >/dev/null
    print_manifest
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
    echo "usage: $0 [--dry-run | --manifest | --render <docs/file.md> | --publish]" >&2
    exit 1
    ;;
esac
