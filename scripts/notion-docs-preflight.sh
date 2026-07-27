#!/usr/bin/env bash
set -euo pipefail

# Read-only Notion Docs Preflight.
#
# Diagnoses the health of the Notion pages that back `governance/notion-page-map.json`
# WITHOUT mutating anything. It never issues create / update / unlock / trash
# requests; it only performs GET requests (`ntn api v1/pages/<id>` and
# `ntn pages get <id> --json`). Page bodies, titles, comments, raw API JSON and
# tokens are processed in memory only and are never written to logs or artifacts.
#
# Two-phase check:
#   Phase 1 (all registered pages): accessible, page id, in_trash, expected parent,
#            lock status — via `ntn api v1/pages/<id>`.
#   Phase 2 (deep targets):        truncated, unknown block count — via
#            `ntn pages get <id> --json`.
#
# Fail-closed: the page map is validated (schema + section counts) before any call;
# explicit deep paths must be registered; a deep base sha must be an existing ancestor
# of HEAD; and Notion responses missing a required field / of the wrong type are
# reported as `schema_invalid` rather than defaulted.
#
# Modes:
#   --check     run the preflight (default). Requires ntn + NOTION_API_TOKEN.
#   --targets   print the resolved phase-2 deep targets and exit (no Notion calls).
#
# Output: a typed, allowed-field-only report to NOTION_PREFLIGHT_RESULT_PATH
# (default notion-preflight-result.json) and a compact table to stdout. Exit code is
# non-zero when any registered page is unhealthy, so the workflow surfaces problems
# while still emitting the full report.

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

MODE="${1:---check}"
PAGE_MAP_PATH="${NOTION_PAGE_MAP_PATH:-governance/notion-page-map.json}"
DEEP_PATHS="${NOTION_PREFLIGHT_DEEP_PATHS:-}"
DEEP_BASE_SHA="${NOTION_PREFLIGHT_DEEP_BASE_SHA:-}"
RESULT_PATH="${NOTION_PREFLIGHT_RESULT_PATH:-notion-preflight-result.json}"
EXPECTED_MARKDOWN_COUNT="${EXPECTED_MARKDOWN_COUNT:-101}"
EXPECTED_GENERAL_COUNT="${EXPECTED_GENERAL_COUNT:-16}"
EXPECTED_ADR_COUNT="${EXPECTED_ADR_COUNT:-85}"
REQUEST_INTERVAL_SECONDS="${NOTION_REQUEST_INTERVAL_SECONDS:-0.4}"
# ntn does not surface HTTP status, so a 403/404 cannot be told apart from a transient
# error. Retries are HARD-capped in retry_ntn (attempts <= 3, each sleep <= 1s, no
# exponential growth) so a run where many pages are inaccessible still finishes within
# the workflow timeout regardless of any environment override.
RETRY_ATTEMPTS="${NOTION_RETRY_ATTEMPTS:-3}"
RETRY_DELAY_SECONDS="${NOTION_RETRY_DELAY_SECONDS:-1}"
RETRY_ATTEMPTS_CAP=3
RETRY_SLEEP_CAP=1

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required command not found: $1" >&2
    exit 1
  }
}

throttle() {
  sleep "$REQUEST_INTERVAL_SECONDS"
}

# Retry wrapper for idempotent GET requests only. Captures ntn's real exit code
# directly (a bare `if ntn; then ... fi` would reset $? to 0 on the failing path).
retry_ntn() {
  local attempt=1
  local status
  local retry_dir
  # Enforce hard upper bounds even if the environment requests larger values, and use a
  # fixed (non-exponential) sleep so total wall-clock is bounded across many pages.
  local max_attempts="$RETRY_ATTEMPTS"
  [ "$max_attempts" -gt "$RETRY_ATTEMPTS_CAP" ] 2>/dev/null && max_attempts="$RETRY_ATTEMPTS_CAP"
  [ "$max_attempts" -ge 1 ] 2>/dev/null || max_attempts=1
  local sleep_s="$RETRY_DELAY_SECONDS"
  [ "$sleep_s" -gt "$RETRY_SLEEP_CAP" ] 2>/dev/null && sleep_s="$RETRY_SLEEP_CAP"
  [ "$sleep_s" -ge 0 ] 2>/dev/null || sleep_s=0
  retry_dir="$(mktemp -d)"
  cat >"$retry_dir/stdin"
  while [ "$attempt" -le "$max_attempts" ]; do
    ntn "$@" <"$retry_dir/stdin" >"$retry_dir/stdout" 2>"$retry_dir/stderr"
    status=$?
    if [ "$status" -eq 0 ]; then
      cat "$retry_dir/stdout"
      rm -rf "$retry_dir"
      return 0
    fi
    if [ "$attempt" -eq "$max_attempts" ]; then
      rm -rf "$retry_dir"
      return "$status"
    fi
    [ "$sleep_s" -gt 0 ] && sleep "$sleep_s"
    attempt=$((attempt + 1))
  done
}

require_command jq
require_command git

if [ ! -f "$PAGE_MAP_PATH" ]; then
  echo "Notion page map not found: $PAGE_MAP_PATH" >&2
  exit 1
fi

# Fail-closed page-map validation: schema, uniqueness, section values and exact counts.
validate_page_map() {
  jq -e \
    --argjson total "$EXPECTED_MARKDOWN_COUNT" \
    --argjson general "$EXPECTED_GENERAL_COUNT" \
    --argjson adr "$EXPECTED_ADR_COUNT" \
    '
    .version == 1
    and (.root_page_id | type == "string" and length > 0)
    and (.adr_page_id | type == "string" and length > 0)
    and (.pages | type == "array")
    and (.pages | length == $total)
    and ([.pages[] | select(.section == "general")] | length == $general)
    and ([.pages[] | select(.section == "adr")] | length == $adr)
    and all(.pages[];
      (.source_path | type == "string" and startswith("docs/") and endswith(".md"))
      and (.section == "general" or .section == "adr")
      and (.state == "active")
      and (.page_id == null or (.page_id | type == "string" and length > 0)))
    and ([.pages[].source_path] | length == (unique | length))
    and ([.pages[] | select(.page_id != null) | .page_id] | length == (unique | length))
    ' "$PAGE_MAP_PATH" >/dev/null || {
    echo "invalid page map (schema/section/count/duplicate): $PAGE_MAP_PATH" >&2
    exit 1
  }
}
validate_page_map

# Canonical page-map validation: exact publication-manifest source/section match +
# `NOTION_PARENT_PAGE_ID == root_page_id`. Reuses the publisher contract
# (`--validate-map`, no Notion calls) so preflight and publish never diverge.
canonical_validate_map() {
  scripts/publish-notion-docs-test.sh --validate-map >&2 || {
    echo "page map failed canonical validation (publish --validate-map)" >&2
    exit 1
  }
}

ROOT_PAGE_ID="$(jq -er '.root_page_id' "$PAGE_MAP_PATH")"
ADR_PAGE_ID="$(jq -er '.adr_page_id' "$PAGE_MAP_PATH")"

# Resolve phase-2 deep targets fail-closed: explicit paths must be registered; a base
# sha must be an existing ancestor of HEAD. Returns the union, intersected with the map.
resolve_deep_targets() {
  local path
  if [ -n "$DEEP_PATHS" ]; then
    while IFS= read -r path; do
      [ -n "$path" ] || continue
      jq -e --arg p "$path" 'any(.pages[]; .source_path == $p)' "$PAGE_MAP_PATH" >/dev/null || {
        echo "deep path is not registered in the page map: $path" >&2
        exit 2
      }
    done < <(printf '%s\n' "$DEEP_PATHS" | tr ',' '\n' | sed '/^[[:space:]]*$/d')
  fi
  if [ -n "$DEEP_BASE_SHA" ]; then
    git cat-file -e "$DEEP_BASE_SHA^{commit}" 2>/dev/null || {
      echo "deep base sha is not a known commit: $DEEP_BASE_SHA" >&2
      exit 2
    }
    git merge-base --is-ancestor "$DEEP_BASE_SHA" HEAD 2>/dev/null || {
      echo "deep base sha is not an ancestor of HEAD: $DEEP_BASE_SHA" >&2
      exit 2
    }
  fi
  {
    if [ -n "$DEEP_PATHS" ]; then
      printf '%s\n' "$DEEP_PATHS" | tr ',' '\n' | sed '/^[[:space:]]*$/d'
    fi
    if [ -n "$DEEP_BASE_SHA" ]; then
      git diff --name-only --diff-filter=ACMRT "$DEEP_BASE_SHA" HEAD -- 'docs/*.md' 'docs/**/*.md'
    fi
  } | LC_ALL=C sort -u | while IFS= read -r path; do
    [ -n "$path" ] || continue
    if jq -e --arg p "$path" 'any(.pages[]; .source_path == $p)' "$PAGE_MAP_PATH" >/dev/null; then
      printf '%s\n' "$path"
    fi
  done
}

if [ "$MODE" = "--targets" ]; then
  canonical_validate_map
  resolve_deep_targets
  exit 0
fi

if [ "$MODE" != "--check" ]; then
  echo "usage: scripts/notion-docs-preflight.sh [--check|--targets]" >&2
  exit 2
fi

require_command ntn
: "${NOTION_API_TOKEN:?NOTION_API_TOKEN is required}"

canonical_validate_map

deep_targets_file="$(mktemp)"
resolve_deep_targets >"$deep_targets_file"

result_jsonl="$(mktemp)"
problems=0

# Emit one typed, allowed-field-only record. Values are already normalized to the JSON
# literals true / false / null / <integer> / "<string>"; no page bodies ever pass here.
emit_record() {
  jq -cn \
    --arg source_path "$1" \
    --arg expected_page_id "$2" \
    --arg actual_id "$3" \
    --argjson accessible "$4" \
    --argjson in_trash "$5" \
    --arg expected_parent_id "$6" \
    --arg actual_parent_id "$7" \
    --argjson is_locked "$8" \
    --argjson truncated "$9" \
    --argjson unknown_block_count "${10}" \
    --arg status "${11}" \
    --arg reason "${12}" \
    '{source_path:$source_path,
      expected_page_id:(if $expected_page_id=="" then null else $expected_page_id end),
      actual_id:(if $actual_id=="" then null else $actual_id end),
      accessible:$accessible,
      in_trash:$in_trash,
      expected_parent_id:$expected_parent_id,
      actual_parent_id:(if $actual_parent_id=="" then null else $actual_parent_id end),
      is_locked:$is_locked,
      truncated:$truncated,
      unknown_block_count:$unknown_block_count,
      status:$status,reason:$reason}' \
    >>"$result_jsonl"
}

while IFS=$'\t' read -r source_path section expected_page_id; do
  if [ "$section" = "general" ]; then
    expected_parent_id="$ROOT_PAGE_ID"
  else
    expected_parent_id="$ADR_PAGE_ID"
  fi

  if [ -z "$expected_page_id" ] || [ "$expected_page_id" = "null" ]; then
    emit_record "$source_path" "" "" false null "$expected_parent_id" "" null null null "unregistered" "page_id is null in page map"
    problems=$((problems + 1))
    continue
  fi

  # Phase 1: metadata only (GET). Preserve accessibility without aborting the run.
  set +e
  page_json="$(retry_ntn api "v1/pages/$expected_page_id" </dev/null 2>/dev/null)"
  api_status=$?
  set -e
  throttle
  if [ "$api_status" -ne 0 ] || [ -z "$page_json" ]; then
    emit_record "$source_path" "$expected_page_id" "" false null "$expected_parent_id" "" null null null "inaccessible" "GET v1/pages failed (403/404 or empty)"
    problems=$((problems + 1))
    continue
  fi

  # Fail-closed schema check: required fields must be present with the right type.
  if ! jq -e '(.id | type == "string")
      and (.in_trash | type == "boolean")
      and (.is_locked | type == "boolean")
      and (.parent | type == "object")
      and (.parent.page_id | type == "string")' <<<"$page_json" >/dev/null; then
    emit_record "$source_path" "$expected_page_id" "" true null "$expected_parent_id" "" null null null "schema_invalid" "page response missing required field or wrong type"
    problems=$((problems + 1))
    continue
  fi

  actual_id="$(jq -r '.id' <<<"$page_json")"
  in_trash="$(jq -r '.in_trash' <<<"$page_json")"
  actual_parent_id="$(jq -r '.parent.page_id // ""' <<<"$page_json")"
  is_locked="$(jq -r '.is_locked' <<<"$page_json")"

  status="ok"
  reason=""
  if [ "$actual_id" != "$expected_page_id" ]; then
    status="id_mismatch"; reason="actual id differs from page map"
  elif [ "$in_trash" = "true" ]; then
    status="in_trash"; reason="page is in trash"
  elif [ "$actual_parent_id" != "$expected_parent_id" ]; then
    status="wrong_parent"; reason="parent differs from expected container"
  elif [ "$is_locked" != "true" ]; then
    status="unlocked"; reason="page is not locked"
  fi

  truncated="null"
  unknown_block_count="null"
  if grep -Fxq "$source_path" "$deep_targets_file"; then
    set +e
    deep_json="$(retry_ntn pages get "$expected_page_id" --json </dev/null 2>/dev/null)"
    deep_status=$?
    set -e
    throttle
    if [ "$deep_status" -ne 0 ] || [ -z "$deep_json" ]; then
      [ "$status" = "ok" ] && { status="deep_unavailable"; reason="pages get failed"; }
    # Fail-closed: truncated must be boolean and unknown_block_ids must be an array.
    elif ! jq -e '(.markdown.truncated | type == "boolean")
        and (.markdown.unknown_block_ids | type == "array")' <<<"$deep_json" >/dev/null; then
      [ "$status" = "ok" ] && { status="schema_invalid"; reason="markdown response missing truncated/unknown_block_ids"; }
    else
      truncated="$(jq -r '.markdown.truncated' <<<"$deep_json")"
      unknown_block_count="$(jq -r '.markdown.unknown_block_ids | length' <<<"$deep_json")"
      if [ "$status" = "ok" ] && [ "$truncated" = "true" ]; then
        status="truncated"; reason="notion returned truncated markdown"
      elif [ "$status" = "ok" ] && [ "$unknown_block_count" != "0" ]; then
        status="unknown_blocks"; reason="page contains unsupported block types"
      fi
    fi
    deep_json=""
  fi

  emit_record "$source_path" "$expected_page_id" "$actual_id" true "$in_trash" \
    "$expected_parent_id" "$actual_parent_id" "$is_locked" "$truncated" "$unknown_block_count" "$status" "$reason"
  [ "$status" != "ok" ] && problems=$((problems + 1))
done < <(jq -r '.pages[] | [.source_path, .section, (.page_id // "")] | @tsv' "$PAGE_MAP_PATH")

# Provenance for the artifact (no bodies/tokens): what commit/map/inputs were checked.
commit_sha="$(git rev-parse HEAD)"
page_map_sha256="$(shasum -a 256 "$PAGE_MAP_PATH" | awk '{print $1}')"
resolved_deep="$(paste -sd ',' "$deep_targets_file" 2>/dev/null || true)"

jq -s \
  --arg commit_sha "$commit_sha" \
  --arg page_map_sha256 "$page_map_sha256" \
  --arg root_page_id "$ROOT_PAGE_ID" \
  --arg adr_page_id "$ADR_PAGE_ID" \
  --arg requested_deep_paths "$DEEP_PATHS" \
  --arg resolved_deep_paths "$resolved_deep" \
  --arg deep_base_sha "$DEEP_BASE_SHA" \
  --argjson problems "$problems" \
  '{commit_sha:$commit_sha, page_map_sha256:$page_map_sha256,
    root_page_id:$root_page_id, adr_page_id:$adr_page_id,
    requested_deep_paths:$requested_deep_paths, resolved_deep_paths:$resolved_deep_paths,
    deep_base_sha:$deep_base_sha, checked:length, problems:$problems, pages:.}' \
  "$result_jsonl" >"$RESULT_PATH"

echo "== Notion Docs Preflight =="
jq -r '.pages[] | [.status, .source_path, (.in_trash|tostring), (.actual_parent_id//"-"), (.is_locked|tostring), (.truncated|tostring), (.unknown_block_count|tostring)] | @tsv' "$RESULT_PATH" \
  | awk -F '\t' '{printf "%-16s %-52s trash=%-5s parent=%-38s locked=%-5s trunc=%-5s unk=%s\n", $1,$2,$3,$4,$5,$6,$7}'
echo "checked=$(jq -r '.checked' "$RESULT_PATH") problems=$problems result=$RESULT_PATH"

# Guard: only the allowed fields may ever leave the process.
unexpected="$(jq -r '.pages[] | keys[]' "$RESULT_PATH" | LC_ALL=C sort -u \
  | grep -vxF -e source_path -e expected_page_id -e actual_id -e accessible -e in_trash \
      -e expected_parent_id -e actual_parent_id -e is_locked -e truncated -e unknown_block_count -e status -e reason || true)"
rm -f "$deep_targets_file" "$result_jsonl"
if [ -n "$unexpected" ]; then
  echo "preflight emitted a non-allowed field: $unexpected" >&2
  exit 3
fi

[ "$problems" -eq 0 ]
