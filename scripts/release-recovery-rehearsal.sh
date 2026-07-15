#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project=""
env_file=""
backup_dir=""

usage() {
  cat <<'EOF'
Usage: release-recovery-rehearsal.sh --project NAME --env-file PATH --backup-dir PATH

The uniquely named production Compose project must already have healthy postgres,
MinIO, Qdrant, and OpenSearch services. Application services should be stopped
while the destructive migration/restore rehearsal runs.
EOF
}

while (($#)); do
  case "$1" in
    --project)
      project="${2:?--project requires a value}"
      shift 2
      ;;
    --env-file)
      env_file="${2:?--env-file requires a value}"
      shift 2
      ;;
    --backup-dir)
      backup_dir="${2:?--backup-dir requires a value}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ -z "$project" || -z "$env_file" || -z "$backup_dir" ]]; then
  usage >&2
  exit 64
fi
if [[ ! "$project" =~ ^m8-release-[a-zA-Z0-9-]+$ ]]; then
  printf 'release project must be uniquely prefixed with m8-release-: %s\n' "$project" >&2
  exit 64
fi
if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 66
fi

mkdir -p "$backup_dir/object-storage"
chmod 0700 "$backup_dir"
chmod 0777 "$backup_dir/object-storage"

read_env() {
  local key="$1"
  local value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$env_file")"
  if [[ -z "$value" ]]; then
    printf 'required release variable missing from env file: %s\n' "$key" >&2
    exit 64
  fi
  printf '%s' "$value"
}

database="$(read_env POSTGRES_DB)"
migration_url="$(read_env NH_DB_MIGRATION_URL)"
ad_bucket="$(read_env AD_ORIGINALS_BUCKET)"
qdrant_collection="$(read_env QDRANT_COLLECTION)"
opensearch_index="$(read_env OPENSEARCH_INDEX)"
redis_probe_key="$(read_env REDIS_QUEUE_PREFIX)m8-release-nondurable-probe"

compose=(
  docker compose
  --project-name "$project"
  --file "$root/compose.yml"
  --file "$root/compose.prod.yml"
  --env-file "$env_file"
)

run_alembic() {
  "${compose[@]}" run --rm --no-deps \
    --env NH_DB_MIGRATION_URL="$migration_url" \
    --volume "$root/apps/backend/alembic.ini:/app/alembic.ini:ro" \
    --volume "$root/apps/backend/migrations:/app/migrations:ro" \
    --entrypoint alembic \
    backend -c /app/alembic.ini "$@"
}

query_postgres() {
  local sql="$1"
  "${compose[@]}" exec -T postgres \
    psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --username migration --dbname "$database" --command "$sql"
}

printf '%s\n' 'M8 migration rehearsal: fresh chain to M7, then M7-to-M8 upgrade'
run_alembic upgrade 0007_m7_validation_kpi
[[ "$(query_postgres 'SELECT version_num FROM app.alembic_version;')" == "0007_m7_validation_kpi" ]]
run_alembic upgrade head
[[ "$(query_postgres 'SELECT version_num FROM app.alembic_version;')" == "0008_m8_support_privileges" ]]

query_postgres \
  "CREATE TABLE app.m8_release_restore_probe (id integer PRIMARY KEY, payload text NOT NULL);
   INSERT INTO app.m8_release_restore_probe VALUES (1, 'provider-free-release-restore');" \
  >/dev/null
postgres_payload="$(query_postgres "SELECT id || ':' || payload FROM app.m8_release_restore_probe;")"
postgres_payload_checksum="$(printf '%s' "$postgres_payload" | sha256sum | cut -d' ' -f1)"

printf '%s\n' 'M8 PostgreSQL backup: backup precedes destructive downgrade'
"${compose[@]}" exec -T postgres \
  pg_dump --username migration --dbname "$database" --format=custom --no-owner \
  >"$backup_dir/postgres.dump"
postgres_dump_checksum="$(sha256sum "$backup_dir/postgres.dump" | cut -d' ' -f1)"
printf '%s  %s\n' "$postgres_dump_checksum" postgres.dump >"$backup_dir/postgres.dump.sha256"

printf '%s\n' 'M8 object-storage backup/restore: private bucket mirror with checksum proof'
"${compose[@]}" run --rm --no-deps \
  --volume "$backup_dir/object-storage:/backup" \
  --entrypoint /bin/sh minio-bootstrap -ec '
    cleanup_backup_permissions() { chmod -R a+rwX /backup || true; }
    trap cleanup_backup_permissions EXIT
    mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
    printf %s provider-free-object-restore > /tmp/m8-release-object
    expected="$(sha256sum /tmp/m8-release-object | cut -d" " -f1)"
    mc cp /tmp/m8-release-object "local/$AD_ORIGINALS_BUCKET/release/m8-restore-probe" >/dev/null
    mc mirror --overwrite "local/$AD_ORIGINALS_BUCKET" /backup >/dev/null
    mc rm --force "local/$AD_ORIGINALS_BUCKET/release/m8-restore-probe" >/dev/null
    mc mirror --overwrite /backup "local/$AD_ORIGINALS_BUCKET" >/dev/null
    mc cp "local/$AD_ORIGINALS_BUCKET/release/m8-restore-probe" /tmp/m8-release-object-restored >/dev/null
    actual="$(sha256sum /tmp/m8-release-object-restored | cut -d" " -f1)"
    test "$actual" = "$expected"
    printf "OBJECT_STORAGE_RESTORED sha256=%s\n" "$actual"
  '
object_checksum="$(sha256sum "$backup_dir/object-storage/release/m8-restore-probe" | cut -d' ' -f1)"

printf '%s\n' 'M8 Qdrant snapshot backup/restore and OpenSearch source rebuild'
chmod 0777 "$backup_dir"
"${compose[@]}" run --rm --no-deps \
  --volume "$backup_dir:/backup" \
  --entrypoint python backend - "$qdrant_collection" "$opensearch_index" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


collection, index = sys.argv[1:]
qdrant = "http://qdrant:6333"
opensearch = "http://opensearch:9200"
snapshot_path = Path("/backup/qdrant.snapshot")


def request_json(method: str, url: str, payload: Any | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.code} {exc.read()!r}") from exc
    return json.loads(data) if data else {}


request_json("DELETE", f"{qdrant}/collections/{collection}")
request_json(
    "PUT",
    f"{qdrant}/collections/{collection}",
    {"vectors": {"size": 3, "distance": "Cosine"}},
)
request_json(
    "PUT",
    f"{qdrant}/collections/{collection}/points?wait=true",
    {
        "points": [
            {
                "id": 4242,
                "vector": [0.1, 0.2, 0.3],
                "payload": {"probe": "provider-free-qdrant-restore"},
            }
        ]
    },
)
snapshot = request_json("POST", f"{qdrant}/collections/{collection}/snapshots?wait=true")
snapshot_name = str(snapshot["result"]["name"])
with urllib.request.urlopen(
    f"{qdrant}/collections/{collection}/snapshots/{snapshot_name}", timeout=30
) as response:
    snapshot_path.write_bytes(response.read())
print(f"QDRANT_SNAPSHOT_BACKED_UP snapshot={snapshot_name}")
PY

qdrant_id="$("${compose[@]}" ps -q qdrant)"
qdrant_checksum="$(sha256sum "$backup_dir/qdrant.snapshot" | cut -d' ' -f1)"
qdrant_node_snapshot="/qdrant/snapshots/$qdrant_collection/m8-release-backup.snapshot"
docker exec --user 0 "$qdrant_id" mkdir -p "/qdrant/snapshots/$qdrant_collection"
docker cp "$backup_dir/qdrant.snapshot" \
  "$qdrant_id:$qdrant_node_snapshot" >/dev/null
qdrant_node_checksum="$(
  docker exec "$qdrant_id" sha256sum "$qdrant_node_snapshot" | cut -d' ' -f1
)"
if [[ "$qdrant_node_checksum" != "$qdrant_checksum" ]]; then
  printf 'Qdrant node-local snapshot checksum mismatch\n' >&2
  exit 1
fi

printf '%s\n' 'M8 Qdrant restore: stop OpenSearch, submit asynchronously, poll restored payload'
"${compose[@]}" stop opensearch
if ! timeout --signal=TERM 240 "${compose[@]}" run --rm --no-deps \
  --entrypoint python backend - "$qdrant_collection" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


collection = sys.argv[1]
qdrant = "http://qdrant:6333"


def request_json(method: str, url: str, payload: Any | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.code} {exc.read()!r}") from exc
    return json.loads(data) if data else {}


request_json("DELETE", f"{qdrant}/collections/{collection}")
restored = request_json(
    "PUT",
    f"{qdrant}/collections/{collection}/snapshots/recover?wait=false",
    {
        "location": f"file:///qdrant/snapshots/{collection}/m8-release-backup.snapshot",
        "priority": "snapshot",
    },
)
submission_accepted = (
    restored.get("result") is True or restored.get("status") == "accepted"
)
if not submission_accepted:
    raise RuntimeError(f"Qdrant snapshot restore failed: {restored!r}")
deadline = time.monotonic() + 180
point: dict[str, Any] = {}
while time.monotonic() < deadline:
    try:
        state = request_json("GET", f"{qdrant}/collections/{collection}")
        if state.get("result", {}).get("status") != "green":
            time.sleep(2)
            continue
        point = request_json("GET", f"{qdrant}/collections/{collection}/points/4242")
    except RuntimeError as exc:
        if "failed: 404" not in str(exc) and "failed: 503" not in str(exc):
            raise
        time.sleep(2)
        continue
    except (urllib.error.URLError, TimeoutError):
        time.sleep(2)
        continue
    if point.get("result", {}).get("payload", {}).get("probe") == "provider-free-qdrant-restore":
        break
    time.sleep(2)
else:
    raise RuntimeError(f"Qdrant restored point did not become ready: {point!r}")
print("QDRANT_RESTORED source=local-file-snapshot")
PY
then
  "${compose[@]}" logs --no-color --tail=80 qdrant >&2 || true
  exit 1
fi

printf '%s\n' 'M8 OpenSearch source rebuild after Qdrant restore'
timeout --signal=TERM 210 "${compose[@]}" \
  up -d --wait --wait-timeout 180 opensearch
timeout --signal=TERM 240 "${compose[@]}" run --rm --no-deps \
  --entrypoint python backend - "$opensearch_index" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any


index = sys.argv[1]
opensearch = "http://opensearch:9200"


def request_json(method: str, url: str, payload: Any | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.code} {exc.read()!r}") from exc
    return json.loads(data) if data else {}

try:
    request_json("DELETE", f"{opensearch}/{index}")
except RuntimeError as exc:
    if "failed: 404" not in str(exc):
        raise
mapping = {
    "mappings": {
        "properties": {
            "probe": {"type": "keyword"},
            "source": {"type": "keyword"},
        }
    }
}
request_json("PUT", f"{opensearch}/{index}", mapping)
request_json(
    "PUT",
    f"{opensearch}/{index}/_doc/m8-release?refresh=true",
    {"probe": "provider-free-opensearch-reindex", "source": "postgres-object-qdrant"},
)
request_json("DELETE", f"{opensearch}/{index}")
request_json("PUT", f"{opensearch}/{index}", mapping)
request_json(
    "PUT",
    f"{opensearch}/{index}/_doc/m8-release?refresh=true",
    {"probe": "provider-free-opensearch-reindex", "source": "postgres-object-qdrant"},
)
document = request_json("GET", f"{opensearch}/{index}/_doc/m8-release")
if document.get("_source", {}).get("probe") != "provider-free-opensearch-reindex":
    raise RuntimeError(f"OpenSearch reindex mismatch: {document!r}")
print("OPENSEARCH_REINDEXED source=postgres-object-qdrant")
PY

printf '%s\n' 'M8 Redis exclusion: queue/cache state is deliberately not backed up'
"${compose[@]}" exec -T redis redis-cli SET "$redis_probe_key" ephemeral >/dev/null
"${compose[@]}" exec -T redis redis-cli FLUSHALL >/dev/null

printf '%s\n' 'M8 lossy rollback: use the pre-existing PostgreSQL backup for recovery'
run_alembic downgrade base
query_postgres 'DROP SCHEMA IF EXISTS app, rag, validation, audit CASCADE;' >/dev/null
cat "$backup_dir/postgres.dump" | "${compose[@]}" exec -T postgres \
  pg_restore --username migration --dbname "$database" --clean --if-exists --no-owner

restored_revision="$(query_postgres 'SELECT version_num FROM app.alembic_version;')"
restored_payload="$(query_postgres "SELECT id || ':' || payload FROM app.m8_release_restore_probe;")"
restored_payload_checksum="$(printf '%s' "$restored_payload" | sha256sum | cut -d' ' -f1)"
if [[ "$restored_revision" != "0008_m8_support_privileges" ]]; then
  printf 'restored migration revision mismatch: %s\n' "$restored_revision" >&2
  exit 1
fi
if [[ "$restored_payload_checksum" != "$postgres_payload_checksum" ]]; then
  printf 'restored PostgreSQL payload checksum mismatch\n' >&2
  exit 1
fi
if [[ "$("${compose[@]}" exec -T redis redis-cli EXISTS "$redis_probe_key" | tr -d '\r')" != "0" ]]; then
  printf 'Redis exclusion failed: nondurable probe was restored\n' >&2
  exit 1
fi

chmod 0700 "$backup_dir"
cat >"$backup_dir/manifest.json" <<EOF
{"schemaVersion":1,"project":"$project","postgres":{"dumpSha256":"$postgres_dump_checksum","payloadSha256":"$restored_payload_checksum","revision":"$restored_revision"},"objectStorage":{"bucket":"$ad_bucket","objectSha256":"$object_checksum"},"qdrant":{"collection":"$qdrant_collection","snapshotSha256":"$qdrant_checksum"},"opensearch":{"index":"$opensearch_index","recovery":"reindex"},"redis":"excluded"}
EOF
manifest_checksum="$(sha256sum "$backup_dir/manifest.json" | cut -d' ' -f1)"
printf 'PASS: M8 recovery rehearsal manifest_sha256=%s postgres=%s object=%s qdrant=%s redis=excluded\n' \
  "$manifest_checksum" "$postgres_dump_checksum" "$object_checksum" "$qdrant_checksum"
