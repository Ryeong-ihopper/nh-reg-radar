#!/usr/bin/env bash
set -euo pipefail

# Contract test for scripts/notion-docs-preflight.sh using a mocked `ntn` CLI.
#
# Diagnosis cases run against the REAL page map (so the reused canonical
# `--validate-map` check passes); the mock resolves each requested page id back to its
# source_path via the map and answers from a per-path scenario table. A second case
# feeds a synthetic (filler) map and asserts preflight rejects it BEFORE any page GET,
# proving canonical validation is wired in. Verifies status classification, fail-closed
# inputs, typed output, that only allow-listed GET calls are made (no mutation), and
# that page bodies / tokens never leave the process. The mock supplies all responses,
# so no real NOTION_API_TOKEN is needed.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
REAL_MAP="governance/notion-page-map.json"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
bin="$work/bin"; mkdir -p "$bin"
call_log="$work/ntn-calls.log"; : >"$call_log"

# Per-source_path scenarios injected onto real pages by the mock.
scenarios="$work/scenarios.json"
cat >"$scenarios" <<'JSON'
{
  "docs/reference-repositories.md": "idmismatch",
  "docs/poc-kpi-formulas.md": "trash",
  "docs/risk-assessment-criteria.md": "wrongparent",
  "docs/poc-evaluation-exclusion-criteria.md": "unlocked",
  "docs/adr-candidates.md": "schemabad",
  "docs/screen-api-mapping.md": "parentless",
  "docs/api-contract-sync-policy.md": "gone",
  "docs/api-specification.md": "truncated",
  "docs/database-specification.md": "unknown",
  "docs/screen-specification.md": "deepschemabad",
  "docs/project-rules.md": "okdeep"
}
JSON

# Mock ntn: records calls; only answers GETs. Resolves id -> source_path via the real
# map, computes the healthy parent from section, then applies the per-path scenario.
cat >"$bin/ntn" <<MOCK
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$call_log"
cat >/dev/null 2>&1 || true
MAP="$REAL_MAP"; SC="$scenarios"

if [ "\$1 \$2" = "api v1/users/me" ]; then printf '%s' '{"id":"u","name":"t"}'; exit 0; fi

lookup() { jq -r --arg id "\$1" '.pages[]|select(.page_id==\$id)|"\(.source_path)\t\(.section)"' "\$MAP"; }
scenario_of() { jq -r --arg sp "\$1" '.[\$sp] // "ok"' "\$SC"; }

if [ "\$1" = "api" ]; then
  id="\${2#v1/pages/}"; row="\$(lookup "\$id")"; sp="\${row%%	*}"; section="\${row##*	}"
  root="\$(jq -r .root_page_id "\$MAP")"; adr="\$(jq -r .adr_page_id "\$MAP")"
  parent="\$root"; [ "\$section" = adr ] && parent="\$adr"
  case "\$(scenario_of "\$sp")" in
    idmismatch)  jq -cn --arg p "\$parent" '{id:"WRONG",in_trash:false,parent:{page_id:\$p},is_locked:true}';;
    trash)       jq -cn --arg id "\$id" --arg p "\$parent" '{id:\$id,in_trash:true,parent:{page_id:\$p},is_locked:true}';;
    wrongparent) jq -cn --arg id "\$id" '{id:\$id,in_trash:false,parent:{page_id:"NOT-THE-PARENT"},is_locked:true}';;
    unlocked)    jq -cn --arg id "\$id" --arg p "\$parent" '{id:\$id,in_trash:false,parent:{page_id:\$p},is_locked:false}';;
    schemabad)   jq -cn --arg id "\$id" --arg p "\$parent" '{id:\$id,parent:{page_id:\$p},is_locked:true}';;
    parentless)  jq -cn --arg id "\$id" '{id:\$id,in_trash:false,parent:{workspace:true},is_locked:true}';;
    gone)        echo 404 >&2; exit 1;;
    *)           jq -cn --arg id "\$id" --arg p "\$parent" '{id:\$id,in_trash:false,parent:{page_id:\$p},is_locked:true}';;
  esac
  exit 0
fi

if [ "\$1" = "pages" ] && [ "\$2" = "get" ]; then
  row="\$(lookup "\$3")"; sp="\${row%%	*}"
  case "\$(scenario_of "\$sp")" in
    truncated)     printf '%s' '{"page":{"id":"x"},"markdown":{"truncated":true,"unknown_block_ids":[],"markdown":"SECRET BODY"}}';;
    unknown)       printf '%s' '{"page":{"id":"x"},"markdown":{"truncated":false,"unknown_block_ids":["b1","b2"],"markdown":"SECRET BODY"}}';;
    deepschemabad) printf '%s' '{"page":{"id":"x"},"markdown":{"truncated":false}}';;
    *)             printf '%s' '{"page":{"id":"x"},"markdown":{"truncated":false,"unknown_block_ids":[],"markdown":"SECRET BODY"}}';;
  esac
  exit 0
fi
echo "unexpected mock ntn call: \$*" >&2; exit 1
MOCK
chmod +x "$bin/ntn"

result="$work/result.json"
fail() { echo "FAIL: $1" >&2; tail -5 "$work/stdout.log" 2>/dev/null; exit 1; }

# --- Case 1: diagnosis against the real (canonical-valid) map --------------------
# Request oversized retry settings; the hard caps (attempts<=3, sleep<=1s) must hold.
t0=$(date +%s)
set +e
env PATH="$bin:$PATH" NTN_CALL_LOG="$call_log" NOTION_API_TOKEN="mock-token" \
  NOTION_PREFLIGHT_RESULT_PATH="$result" NOTION_REQUEST_INTERVAL_SECONDS=0 \
  NOTION_RETRY_ATTEMPTS=99 NOTION_RETRY_DELAY_SECONDS=99 \
  NOTION_PREFLIGHT_DEEP_PATHS="docs/api-specification.md,docs/database-specification.md,docs/screen-specification.md,docs/project-rules.md" \
  scripts/notion-docs-preflight.sh --check >"$work/stdout.log" 2>"$work/stderr.log"
exit_code=$?
set -e
elapsed=$(( $(date +%s) - t0 ))

status_of() { jq -r --arg p "$1" '.pages[]|select(.source_path==$p)|.status' "$result"; }
[ "$(status_of docs/reference-repositories.md)" = "id_mismatch" ]            || fail "id_mismatch"
[ "$(status_of docs/poc-kpi-formulas.md)" = "in_trash" ]                     || fail "in_trash"
[ "$(status_of docs/risk-assessment-criteria.md)" = "wrong_parent" ]        || fail "wrong_parent"
[ "$(status_of docs/poc-evaluation-exclusion-criteria.md)" = "unlocked" ]   || fail "unlocked"
[ "$(status_of docs/adr-candidates.md)" = "schema_invalid" ]                || fail "schema_invalid phase1"
[ "$(status_of docs/screen-api-mapping.md)" = "schema_invalid" ]            || fail "schema_invalid parentless"
[ "$(status_of docs/api-contract-sync-policy.md)" = "inaccessible" ]   || fail "inaccessible"
[ "$(status_of docs/api-specification.md)" = "truncated" ]                  || fail "truncated"
[ "$(status_of docs/database-specification.md)" = "unknown_blocks" ]        || fail "unknown_blocks"
[ "$(status_of docs/screen-specification.md)" = "schema_invalid" ]          || fail "schema_invalid deep"
[ "$(status_of docs/project-rules.md)" = "ok" ]                             || fail "ok(deep healthy)"

# typed output
jq -e '.pages[]|select(.source_path=="docs/project-rules.md")|.in_trash==false and .is_locked==true and .truncated==false and .unknown_block_count==0 and .accessible==true' "$result" >/dev/null || fail "typed ok"
jq -e '.pages[]|select(.source_path=="docs/database-specification.md")|.unknown_block_count==2' "$result" >/dev/null || fail "unknown int"
jq -e '.pages[]|select(.source_path=="docs/poc-kpi-formulas.md")|.truncated==null and .unknown_block_count==null' "$result" >/dev/null || fail "non-deep null"
jq -e '.pages[]|select(.source_path=="docs/api-contract-sync-policy.md")|.accessible==false and .actual_id==null' "$result" >/dev/null || fail "inaccessible nulls"
# provenance + non-zero exit
jq -e '.commit_sha and .page_map_sha256 and (.resolved_deep_paths|length>0)' "$result" >/dev/null || fail "provenance"
[ "$exit_code" -ne 0 ] || fail "expected non-zero exit"

# retry hard caps: an inaccessible page is retried at most 3 times and, despite the
# oversized delay request, the whole run stays fast (fixed <=1s sleeps, no exponential).
gone_id="$(jq -r '.pages[]|select(.source_path=="docs/api-contract-sync-policy.md").page_id' "$REAL_MAP")"
gone_calls="$(grep -cxF "api v1/pages/$gone_id" "$call_log" || true)"
[ "$gone_calls" -eq 3 ] || fail "retry attempts not capped at 3 (got $gone_calls)"
[ "$elapsed" -lt 30 ] || fail "retry sleep not capped (elapsed ${elapsed}s with delay=99)"

# only allow-listed GET calls were made (no mutation of any kind)
if grep -vE '^(api v1/users/me|api v1/pages/[^ ]+|pages get [^ ]+ --json)$' "$call_log" | grep -q .; then
  grep -vE '^(api v1/users/me|api v1/pages/[^ ]+|pages get [^ ]+ --json)$' "$call_log"; fail "non-allowlisted ntn call"
fi
# no body / token leak in result, stdout or stderr
grep -q "SECRET BODY" "$result" "$work/stdout.log" "$work/stderr.log" && fail "body leaked"
grep -q "mock-token" "$result" "$work/stdout.log" "$work/stderr.log" && fail "token leaked"
# only allowed fields
unexpected="$(jq -r '.pages[]|keys[]' "$result" | LC_ALL=C sort -u \
  | grep -vxF -e source_path -e expected_page_id -e actual_id -e accessible -e in_trash \
      -e expected_parent_id -e actual_parent_id -e is_locked -e truncated -e unknown_block_count -e status -e reason || true)"
[ -z "$unexpected" ] || fail "non-allowed field: $unexpected"

# --- Case 2: canonical validation rejects a filler map before any Notion GET ------
fake="$work/fake-map.json"
python3 - "$fake" <<'PY'
import json, sys
pages=[{"source_path":f"docs/filler-{i}.md","section":"general","page_id":f"f{i}","state":"active"} for i in range(17)]
pages+=[{"source_path":f"docs/adr/ADR-{i:04d}.md","section":"adr","page_id":f"a{i}","state":"active"} for i in range(85)]
json.dump({"version":1,"root_page_id":"ROOT","adr_page_id":"ADR","last_published_commit":"0"*40,"pages":pages},open(sys.argv[1],"w"))
PY
: >"$call_log"
set +e
env PATH="$bin:$PATH" NTN_CALL_LOG="$call_log" NOTION_API_TOKEN="mock-token" \
  NOTION_PAGE_MAP_PATH="$fake" NOTION_PREFLIGHT_RESULT_PATH="$work/fake.json" NOTION_REQUEST_INTERVAL_SECONDS=0 \
  scripts/notion-docs-preflight.sh --check >/dev/null 2>&1
fake_code=$?
set -e
[ "$fake_code" -ne 0 ] || fail "filler map must be rejected"
grep -Eq '^(api v1/pages/|pages get )' "$call_log" && fail "filler map reached Notion page GET (canonical validation not wired)"

# --- Case 3: fail-closed deep inputs ---------------------------------------------
set +e
NOTION_PREFLIGHT_DEEP_PATHS="docs/not-in-map.md" scripts/notion-docs-preflight.sh --targets >/dev/null 2>&1; c1=$?
NOTION_PREFLIGHT_DEEP_BASE_SHA="deadbeef" scripts/notion-docs-preflight.sh --targets >/dev/null 2>&1; c2=$?
set -e
[ "$c1" -eq 2 ] || fail "unregistered deep path should exit 2"
[ "$c2" -eq 2 ] || fail "bad base sha should exit 2"

echo "notion preflight script contract passed"
