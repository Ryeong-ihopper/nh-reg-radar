#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

MODE="${1:---publish}"
REPOSITORY="${GITHUB_REPOSITORY:-CGINSIDE-ROOKIES/nh-ad-compliance}"
COMMIT_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
EXPECTED_MARKDOWN_COUNT="${EXPECTED_MARKDOWN_COUNT:-102}"
EXPECTED_GENERAL_COUNT="${EXPECTED_GENERAL_COUNT:-17}"
EXPECTED_ADR_COUNT="${EXPECTED_ADR_COUNT:-85}"
EXPECTED_EXCLUDED_MARKDOWN_COUNT="${EXPECTED_EXCLUDED_MARKDOWN_COUNT:-33}"
EXPECTED_PARENT_TITLE="${EXPECTED_NOTION_PARENT_TITLE:-개발 문서}"
PAGE_MAP_PATH="${NOTION_PAGE_MAP_PATH:-governance/notion-page-map.json}"
SYNC_BASE_SHA="${NOTION_SYNC_BASE_SHA:-}"
SYNC_PATHS="${NOTION_SYNC_PATHS:-}"
ALLOW_CREATE="${NOTION_ALLOW_CREATE:-0}"
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

list_tracked_markdown_files() {
  git ls-files -- 'docs/*.md' 'docs/**/*.md' | LC_ALL=C sort
}

list_excluded_markdown_files() {
  # Repository-internal handoff, audit and work-log documents are Git source
  # material, but are not part of the established 102-page Notion share set.
  # ADR-0084 through ADR-0089 remain excluded until page IDs are provisioned and
  # the publication contract is deliberately expanded.
  printf '%s\n' \
    docs/adr/ADR-0084-python-311-dual-gpu-runtime-profiles.md \
    docs/adr/ADR-0085-source-structure-and-evidence-bundles.md \
    docs/adr/ADR-0086-source-bound-review-program-runtime.md \
    docs/adr/ADR-0087-product-composition-and-evidence-policy.md \
    docs/adr/ADR-0088-hwp-html-review-display.md \
    docs/adr/ADR-0089-irp-fund-component-composition.md \
    docs/codebase-structure-current.md \
    docs/custom-parser-audit-current.md \
    docs/decisions.md \
    docs/evaluation-splits-current.md \
    docs/first-review-local-spark-guide.md \
    docs/handoff-current.md \
    docs/intake-routing-template-review-2026-09-09.md \
    docs/new-team-member-overview.md \
    docs/parser-agent-handoff.md \
    docs/parser-handoff-quickstart.md \
    docs/parser-integration-audit-2026-09-10.md \
    docs/parser-integration-audit-2026-09-22.md \
    docs/parser-schema-change-request-current.md \
    docs/parser-schema-current-2026-09-28.md \
    docs/pipeline-design-review-current.md \
    docs/review-flow-and-structuring-2026-09-28.md \
    docs/rule-execution-contract-current.md \
    docs/runtime-wiring-audit-2026-09-22.md \
    docs/session-resume-prompt.md \
    docs/work-log-2026-09-14.md \
    docs/work-log-2026-09-15.md \
    docs/work-log-2026-09-16.md \
    docs/work-log-2026-09-17.md \
    docs/work-log-2026-09-18.md \
    docs/work-log-2026-09-21.md \
    docs/work-log-2026-09-22.md \
    docs/work-log-2026-09-28.md
}

list_general_files() {
  printf '%s\n' \
    docs/project-rules.md \
    docs/requirements-definition.md \
    docs/functional-specification.md \
    docs/screen-specification.md \
    docs/screen-api-mapping.md \
    docs/api-specification.md \
    docs/api-contract-sync-policy.md \
    docs/database-specification.md \
    docs/test-cases.md \
    docs/adr-candidates.md \
    docs/development-schedule-and-notion-kanban.md \
    docs/reference-repositories.md \
    docs/poc-kpi-formulas.md \
    docs/poc-evaluation-exclusion-criteria.md \
    docs/risk-assessment-criteria.md \
    docs/self-hosted-runner-guide.md \
    docs/architecture-overview.md
}

list_adr_files() {
  printf '%s\n' docs/adr/README.md docs/adr/decision-questions.md
  comm -23 \
    <(git ls-files -- 'docs/adr/ADR-*.md' | LC_ALL=C sort) \
    <(list_excluded_markdown_files | LC_ALL=C sort)
}

list_markdown_files() {
  printf '%s\n' "$(list_general_files)" "$(list_adr_files)" | LC_ALL=C sort
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
  if [ "$section" = "general" ] && [ "$order" = "00" ]; then
    printf '%s\n' "$title"
  elif [ "$source_path" = "docs/self-hosted-runner-guide.md" ] || [ "$source_path" = "docs/architecture-overview.md" ]; then
    printf '참고. %s\n' "$title"
  elif [ "$section" = "general" ] || [ "$order" = "00" ] || [ "$order" = "01" ]; then
    printf '%s. %s\n' "$order" "$title"
  else
    printf '%s\n' "$title"
  fi
}

print_manifest() {
  local source_path
  local order=0
  local order_label

  printf 'general\t00\t%s\t%s\n' \
    docs/project-rules.md "$(display_title general 00 docs/project-rules.md)"

  while IFS= read -r source_path; do
    if [ "$source_path" = "docs/project-rules.md" ]; then
      continue
    fi
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
  local excluded_count
  local source_path
  local title

  selected_count="$(list_markdown_files | wc -l | tr -d ' ')"
  general_count="$(list_general_files | wc -l | tr -d ' ')"
  adr_count="$(list_adr_files | wc -l | tr -d ' ')"
  excluded_count="$(list_excluded_markdown_files | wc -l | tr -d ' ')"

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
  if [ "$excluded_count" -ne "$EXPECTED_EXCLUDED_MARKDOWN_COUNT" ]; then
    echo "expected $EXPECTED_EXCLUDED_MARKDOWN_COUNT excluded Markdown files, found $excluded_count" >&2
    exit 1
  fi
  if ! diff -u \
    <(list_tracked_markdown_files) \
    <(printf '%s\n' "$(list_markdown_files)" "$(list_excluded_markdown_files)" | LC_ALL=C sort) >/dev/null; then
    echo "tracked Markdown set is not fully classified as published or excluded" >&2
    exit 1
  fi
  if comm -12 \
    <(list_markdown_files) \
    <(list_excluded_markdown_files | LC_ALL=C sort) | grep -q .; then
    echo "published and excluded Markdown sets overlap" >&2
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
  printf 'excluded_markdown_count=%s\n' "$excluded_count"
  printf 'excluded_non_markdown_count=%s\n' "$(count_non_markdown_files)"
}

validate_page_map() {
  local manifest_file
  local map_sources
  local manifest_sources

  if [ ! -f "$PAGE_MAP_PATH" ]; then
    echo "Notion page map not found: $PAGE_MAP_PATH" >&2
    exit 1
  fi

  jq -e '
    .version == 1
    and (.root_page_id | type == "string" and length > 0)
    and (.adr_page_id | type == "string" and length > 0)
    and (.last_published_commit | type == "string" and test("^[0-9a-f]{40}$"))
    and (.pages | type == "array")
    and all(.pages[];
      (.source_path | type == "string" and startswith("docs/") and endswith(".md"))
      and (.section == "general" or .section == "adr")
      and (.state == "active")
      and (.page_id == null or (.page_id | type == "string" and length > 0)))
    and ([.pages[].source_path] | length == (unique | length))
    and ([.pages[] | select(.page_id != null) | .page_id] | length == (unique | length))
  ' "$PAGE_MAP_PATH" >/dev/null || {
    echo "invalid or duplicate Notion page map: $PAGE_MAP_PATH" >&2
    exit 1
  }

  manifest_file="$(mktemp)"
  print_manifest >"$manifest_file"
  manifest_sources="$(awk -F '\t' '{print $3 "\t" $1}' "$manifest_file" | LC_ALL=C sort)"
  map_sources="$(jq -r '.pages[] | [.source_path,.section] | @tsv' "$PAGE_MAP_PATH" | LC_ALL=C sort)"
  rm -f "$manifest_file"

  if ! diff -u <(printf '%s\n' "$manifest_sources") <(printf '%s\n' "$map_sources") >&2; then
    echo "Notion page map must cover the publication manifest exactly" >&2
    exit 1
  fi

  if [ -n "${NOTION_PARENT_PAGE_ID:-}" ] \
    && [ "$(jq -r '.root_page_id' "$PAGE_MAP_PATH")" != "$NOTION_PARENT_PAGE_ID" ]; then
    echo "NOTION_PARENT_PAGE_ID does not match the reviewed page map" >&2
    exit 1
  fi
}

list_sync_paths() {
  local deleted_paths

  if [ -n "$SYNC_PATHS" ]; then
    printf '%s\n' "$SYNC_PATHS" | tr ',' '\n' | sed '/^[[:space:]]*$/d' | LC_ALL=C sort -u
    return
  fi

  if [ -z "$SYNC_BASE_SHA" ]; then
    echo "NOTION_SYNC_BASE_SHA or NOTION_SYNC_PATHS is required" >&2
    exit 1
  fi
  if ! git cat-file -e "$SYNC_BASE_SHA^{commit}" 2>/dev/null; then
    echo "Notion sync base commit is unavailable: $SYNC_BASE_SHA" >&2
    exit 1
  fi

  deleted_paths="$({ git diff --name-only --diff-filter=D "$SYNC_BASE_SHA" "$COMMIT_SHA" -- 'docs/*.md' 'docs/**/*.md' || true; } | sed '/^$/d')"
  if [ -n "$deleted_paths" ]; then
    echo "deleted Notion documents require a reviewed page-map/archive change:" >&2
    printf '%s\n' "$deleted_paths" >&2
    exit 1
  fi

  git diff --name-only --diff-filter=ACMRT "$SYNC_BASE_SHA" "$COMMIT_SHA" \
    -- 'docs/*.md' 'docs/**/*.md' \
    | while IFS= read -r source_path; do
        [ -f "$source_path" ] && printf '%s\n' "$source_path"
      done \
    | LC_ALL=C sort -u
}

validate_sync_paths() {
  local sync_file="$1"
  local source_path

  while IFS= read -r source_path; do
    [ -z "$source_path" ] && continue
    if ! print_manifest | awk -F '\t' -v source_path="$source_path" '$3 == source_path {found=1} END {exit !found}'; then
      echo "sync path is not in the publication manifest: $source_path" >&2
      exit 1
    fi
  done <"$sync_file"
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

unlock_page() {
  local page_id="$1"

  jq -n '{is_locked:false}' \
    | retry_ntn api "v1/pages/$page_id" -X PATCH --data @- \
    | jq -e '.is_locked == false' >/dev/null
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

replace_page_markdown() {
  local page_id="$1"
  local markdown_file="$2"

  retry_ntn pages update "$page_id" <"$markdown_file" >/dev/null
  throttle
}

verify_document_page() {
  local page_id="$1"
  local title="$2"
  local source_path="$3"
  local verification
  local probe

  verification="$(retry_ntn pages get "$page_id" --json </dev/null)"
  throttle
  probe="$(content_probe "$source_path")"

  if ! jq -e \
    --arg page_id "$page_id" \
    --arg title "$title" \
    --arg probe "$probe" \
    '(.page.id // $page_id) == $page_id
      and .page.is_locked == true
      and .page.in_trash != true
      and .page.properties.title.title[0].plain_text == $title
      and .markdown.truncated == false
      and (.markdown.unknown_block_ids | length == 0)
      and (.markdown.markdown | contains($probe))' \
    <<<"$verification" >/dev/null; then
    echo "Notion synchronization verification failed: $source_path" >&2
    return 1
  fi

  printf '%s\n' "$verification"
}

restore_document_page() {
  local page_id="$1"
  local previous_title="$2"
  local previous_markdown_file="$3"

  echo "restoring Notion page after failed synchronization: $page_id" >&2
  unlock_page "$page_id" || true
  replace_page_markdown "$page_id" "$previous_markdown_file" || true
  set_page_title "$page_id" "$previous_title" || true
  lock_page "$page_id" || true
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

update_document() {
  local section="$1"
  local order="$2"
  local source_path="$3"
  local title="$4"
  local expected_parent_id="$5"
  local page_id="$6"
  local result_jsonl="$7"
  local temp_dir
  local new_markdown_file
  local previous_markdown_file
  local before
  local verification
  local previous_title
  local page_url
  local source_hash

  echo "synchronizing [$section/$order] $source_path -> $page_id"
  temp_dir="$(mktemp -d)"
  new_markdown_file="$temp_dir/new.md"
  previous_markdown_file="$temp_dir/previous.md"
  render_markdown "$source_path" >"$new_markdown_file"

  before="$(retry_ntn pages get "$page_id" --json </dev/null)"
  throttle
  if ! jq -e --arg page_id "$page_id" --arg parent_id "$expected_parent_id" \
    '.page.id == $page_id
      and .page.in_trash != true
      and .page.parent.page_id == $parent_id
      and .markdown.truncated == false
      and (.markdown.unknown_block_ids | length == 0)' \
    <<<"$before" >/dev/null; then
    echo "mapped Notion page is missing, truncated, unknown, or under the wrong parent: $source_path" >&2
    rm -rf "$temp_dir"
    return 1
  fi

  previous_title="$(jq -er '.page.properties.title.title[0].plain_text' <<<"$before")"
  page_url="$(jq -er '.page.url' <<<"$before")"
  jq -r '.markdown.markdown' <<<"$before" >"$previous_markdown_file"

  if unlock_page "$page_id" \
    && replace_page_markdown "$page_id" "$new_markdown_file" \
    && set_page_title "$page_id" "$title" \
    && lock_page "$page_id" \
    && verification="$(verify_document_page "$page_id" "$title" "$source_path")"; then
    source_hash="$(shasum -a 256 "$source_path" | awk '{print $1}')"
    jq -cn \
      --arg action updated \
      --arg section "$section" \
      --arg order "$order" \
      --arg source_path "$source_path" \
      --arg display_title "$title" \
      --arg source_sha256 "$source_hash" \
      --arg page_id "$page_id" \
      --arg page_url "$page_url" \
      '{action:$action,section:$section,order:$order,source_path:$source_path,display_title:$display_title,source_sha256:$source_sha256,page_id:$page_id,page_url:$page_url,is_locked:true,verified:true}' \
      >>"$result_jsonl"
    rm -rf "$temp_dir"
    return 0
  fi

  restore_document_page "$page_id" "$previous_title" "$previous_markdown_file"
  rm -rf "$temp_dir"
  return 1
}

create_document_for_sync() {
  local section="$1"
  local order="$2"
  local source_path="$3"
  local title="$4"
  local parent_page_id="$5"
  local result_jsonl="$6"
  local page_response
  local page_id=""
  local page_url
  local source_hash

  echo "creating reviewed Notion mapping [$section/$order] $source_path"
  unlock_page "$parent_page_id"

  if page_response="$(render_markdown "$source_path" \
    | ntn pages create --parent "page:$parent_page_id" --json)"; then
    page_id="$(jq -er '.id' <<<"$page_response")"
    page_url="$(jq -er '.url' <<<"$page_response")"
    throttle
  fi

  if [ -n "$page_id" ] \
    && set_page_title "$page_id" "$title" \
    && lock_page "$page_id" \
    && verify_document_page "$page_id" "$title" "$source_path" >/dev/null \
    && lock_page "$parent_page_id"; then
    source_hash="$(shasum -a 256 "$source_path" | awk '{print $1}')"
    jq -cn \
      --arg action created \
      --arg section "$section" \
      --arg order "$order" \
      --arg source_path "$source_path" \
      --arg display_title "$title" \
      --arg source_sha256 "$source_hash" \
      --arg page_id "$page_id" \
      --arg page_url "$page_url" \
      '{action:$action,section:$section,order:$order,source_path:$source_path,display_title:$display_title,source_sha256:$source_sha256,page_id:$page_id,page_url:$page_url,is_locked:true,verified:true}' \
      >>"$result_jsonl"
    return 0
  fi

  if [ -n "$page_id" ]; then
    jq -n '{in_trash:true}' \
      | retry_ntn api "v1/pages/$page_id" -X PATCH --data @- >/dev/null || true
    throttle
  fi
  lock_page "$parent_page_id" || true
  return 1
}

validate_sync_container() {
  local page_id="$1"
  local expected_title="$2"
  local response

  response="$(retry_ntn api "v1/pages/$page_id" </dev/null)"
  throttle
  jq -e --arg title "$expected_title" \
    '.in_trash == false and (.properties.title.title[0].plain_text // "") == $title' \
    <<<"$response" >/dev/null
}

sync_documents() {
  local root_page_id
  local adr_page_id
  local root_page_url
  local sync_file
  local result_jsonl
  local temp_dir
  local section
  local order
  local source_path
  local title
  local page_id
  local parent_page_id
  local synced_count

  require_command jq
  require_command ntn
  require_command perl
  require_command shasum

  : "${NOTION_API_TOKEN:?NOTION_API_TOKEN is required}"
  : "${NOTION_PARENT_PAGE_ID:?NOTION_PARENT_PAGE_ID is required}"

  validate_selection >/dev/null
  validate_page_map
  root_page_id="$(jq -er '.root_page_id' "$PAGE_MAP_PATH")"
  adr_page_id="$(jq -er '.adr_page_id' "$PAGE_MAP_PATH")"
  validate_sync_container "$root_page_id" "$EXPECTED_PARENT_TITLE"
  validate_sync_container "$adr_page_id" '15. ADR'
  root_page_url="$(retry_ntn api "v1/pages/$root_page_id" </dev/null | jq -er '.url')"
  throttle

  temp_dir="$(mktemp -d)"
  sync_file="$temp_dir/sync-paths"
  result_jsonl="$temp_dir/results.jsonl"
  : >"$result_jsonl"
  list_sync_paths >"$sync_file"
  validate_sync_paths "$sync_file"

  if [ "$ALLOW_CREATE" = "1" ]; then
    local create_path_count
    local create_path
    local create_mapped_id
    create_path_count="$(grep -c . "$sync_file" || true)"
    if [ -z "$SYNC_PATHS" ] || [ "$create_path_count" -ne 1 ]; then
      echo "allow_create requires exactly one explicit NOTION_SYNC_PATHS entry (one page per run)" >&2
      rm -rf "$temp_dir"
      exit 1
    fi
    create_path="$(sed -n '1p' "$sync_file")"
    create_mapped_id="$(jq -r --arg p "$create_path" '.pages[] | select(.source_path == $p) | .page_id // "null"' "$PAGE_MAP_PATH")"
    if [ "$create_mapped_id" != "null" ]; then
      echo "allow_create target is already mapped; creation not needed: $create_path" >&2
      rm -rf "$temp_dir"
      exit 1
    fi
  fi

  while IFS=$'\t' read -r section order source_path title; do
    if ! grep -Fxq "$source_path" "$sync_file"; then
      continue
    fi
    page_id="$(jq -r --arg source_path "$source_path" '.pages[] | select(.source_path == $source_path) | .page_id // empty' "$PAGE_MAP_PATH")"
    if [ "$section" = "general" ]; then
      parent_page_id="$root_page_id"
    else
      parent_page_id="$adr_page_id"
    fi

    if [ -n "$page_id" ]; then
      update_document "$section" "$order" "$source_path" "$title" \
        "$parent_page_id" "$page_id" "$result_jsonl"
    elif [ "$ALLOW_CREATE" = "1" ]; then
      create_document_for_sync "$section" "$order" "$source_path" "$title" \
        "$parent_page_id" "$result_jsonl"
    else
      echo "Notion page mapping is missing and automatic creation is disabled: $source_path" >&2
      rm -rf "$temp_dir"
      exit 1
    fi
  done < <(print_manifest)

  # Write the result artifact before final container locks so created/updated
  # page IDs are always recoverable even if a later locking step fails.
  jq -s \
    --arg root_page_id "$root_page_id" \
    --arg root_page_url "$root_page_url" \
    --arg adr_page_id "$adr_page_id" \
    --arg base_commit "$SYNC_BASE_SHA" \
    --arg commit_sha "$COMMIT_SHA" \
    '{root_page_id:$root_page_id,root_page_url:$root_page_url,adr_page_id:$adr_page_id,base_commit:$base_commit,commit_sha:$commit_sha,synced_count:length,pages:.}' \
    "$result_jsonl" >notion-sync-result.json

  lock_page "$adr_page_id"
  lock_page "$root_page_id"

  synced_count="$(jq -r '.synced_count' notion-sync-result.json)"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'root_page_url=%s\n' "$root_page_url" >>"$GITHUB_OUTPUT"
    printf 'synced_count=%s\n' "$synced_count" >>"$GITHUB_OUTPUT"
  fi
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      printf '## Notion 개발 문서 동기화\n\n'
      printf -- '- 개발 문서: [%s](%s)\n' "$EXPECTED_PARENT_TITLE" "$root_page_url"
      printf -- '- 기준 commit: `%s`\n' "$SYNC_BASE_SHA"
      printf -- '- 대상 commit: `%s`\n' "$COMMIT_SHA"
      printf -- '- 갱신 문서: %s개\n' "$synced_count"
    } >>"$GITHUB_STEP_SUMMARY"
  fi

  printf 'root_page_url=%s\n' "$root_page_url"
  printf 'synced_count=%s\n' "$synced_count"
  rm -rf "$temp_dir"
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
  done < <(print_manifest | awk -F '\t' '$1 == "general" && $2 == "00"')

  append_divider "$NOTION_PARENT_PAGE_ID" >>"$cleanup_divider_ids"

  while IFS=$'\t' read -r section order source_path title; do
    publish_document "$section" "$order" "$source_path" "$title" \
      "$NOTION_PARENT_PAGE_ID" "$result_jsonl" "$cleanup_page_ids"
  done < <(print_manifest | awk -F '\t' '$1 == "general" && $2 != "00"')

  append_divider "$NOTION_PARENT_PAGE_ID" >>"$cleanup_divider_ids"
  adr_response="$(create_container_page "$NOTION_PARENT_PAGE_ID" '15. ADR')"
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
  --validate-map)
    validate_selection >/dev/null
    validate_page_map
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
  --sync)
    sync_documents
    ;;
  *)
    echo "usage: $0 [--dry-run | --manifest | --validate-map | --render <docs/file.md> | --publish | --sync]" >&2
    exit 1
    ;;
esac
