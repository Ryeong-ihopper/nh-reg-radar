hash_directory() {
  local directory="$1"

  python3 - "$directory" "$HASH_FILE" <<'PY'
from __future__ import annotations

import hashlib
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
marker = sys.argv[2]
paths = [root, *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())]
digest = hashlib.sha256()
for path in paths:
    if path == root / marker:
        continue
    relative = "." if path == root else path.relative_to(root).as_posix()
    mode = path.lstat().st_mode
    if stat.S_ISDIR(mode):
        kind = b"directory"
        content = b""
    elif stat.S_ISREG(mode):
        kind = b"file"
        content = path.read_bytes()
    else:
        print(f"unsupported file type: {path}", file=sys.stderr)
        raise SystemExit(2)
    digest.update(kind)
    digest.update(b"\0")
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(f"{stat.S_IMODE(mode):04o}".encode("ascii"))
    digest.update(b"\0")
    digest.update(content)
    digest.update(b"\0")

print(digest.hexdigest())
PY
}

relative_source() {
  local skill_name="$1"
  printf '../../skills/%s\n' "$skill_name"
}

validate_skill_sources() {
  local source
  local skill_name
  local nested_link
  local unsupported_file

  if [ ! -d "$SOURCE_ROOT" ] || [ -L "$SOURCE_ROOT" ]; then
    echo "skills source directory must be a local directory: $SOURCE_ROOT" >&2
    return 1
  fi

  for source in "$SOURCE_ROOT"/*; do
    if [ -L "$source" ]; then
      echo "skill source must not be a symbolic link: $source" >&2
      return 1
    fi
    [ -d "$source" ] || continue
    [ -f "$source/SKILL.md" ] || continue
    skill_name="$(basename "$source")"
    if [[ ! "$skill_name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
      echo "invalid skill directory name: $source" >&2
      return 1
    fi
    nested_link="$(find "$source" -type l -print -quit)"
    if [ -n "$nested_link" ]; then
      echo "skill source contains a symbolic link: $nested_link" >&2
      return 1
    fi
    unsupported_file="$(find "$source" ! -type d ! -type f ! -type l -print -quit)"
    if [ -n "$unsupported_file" ]; then
      echo "unsupported file type: $unsupported_file" >&2
      return 1
    fi
  done
}

ensure_adapter_root() {
  local adapter_root="$1"
  local create="$2"
  local parent
  local canonical_root
  local canonical_adapter
  local expected_adapter

  parent="$(dirname "$adapter_root")"
  if [ -L "$parent" ] || [ -L "$adapter_root" ]; then
    echo "adapter path must not be a symbolic link: $adapter_root" >&2
    return 1
  fi
  if { [ -e "$parent" ] && [ ! -d "$parent" ]; } ||
    { [ -e "$adapter_root" ] && [ ! -d "$adapter_root" ]; }; then
    echo "adapter path must be a directory: $adapter_root" >&2
    return 1
  fi

  if [ "$create" = "true" ]; then
    mkdir -p "$adapter_root"
  elif [ ! -d "$adapter_root" ]; then
    echo "missing adapter directory: $adapter_root; run scripts/setup-dev-tools.sh" >&2
    return 1
  fi

  canonical_root="$(cd "$ROOT" && pwd -P)"
  canonical_adapter="$(cd "$adapter_root" && pwd -P)"
  expected_adapter="$canonical_root/${adapter_root#"$ROOT/"}"
  if [ "$canonical_adapter" != "$expected_adapter" ]; then
    echo "adapter path escapes repository: $adapter_root" >&2
    return 1
  fi
}

has_managed_copy_metadata() {
  local target="$1"
  local skill_name="$2"
  local nested_link
  local source_line
  local hash_line

  [ -d "$target" ] && [ ! -L "$target" ] && [ -f "$target/$HASH_FILE" ] || return 1
  source_line="$(sed -n '1p' "$target/$HASH_FILE")"
  hash_line="$(sed -n '2p' "$target/$HASH_FILE")"
  [ "$source_line" = "source=skills/$skill_name" ] || return 1
  [[ "$hash_line" =~ ^hash=[0-9a-f]{64}$ ]] || return 1
  printf '%s\n%s\n' "$source_line" "$hash_line" | cmp -s - "$target/$HASH_FILE" || return 1
  nested_link="$(find "$target" -type l -print -quit)"
  [ -z "$nested_link" ]
}

is_managed_copy() {
  local target="$1"
  local skill_name="$2"
  local recorded_hash

  has_managed_copy_metadata "$target" "$skill_name" || return 1
  recorded_hash="$(sed -n 's/^hash=//p' "$target/$HASH_FILE")"
  [ "$(hash_directory "$target")" = "$recorded_hash" ]
}
