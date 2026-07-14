validate_replaceable_target() {
  local target="$1"
  local expected_link="$2"
  local skill_name="$3"

  if [ -L "$target" ]; then
    if [ "$(readlink "$target")" != "$expected_link" ]; then
      echo "unmanaged adapter collision: $target" >&2
      return 1
    fi
    return
  fi

  if is_managed_copy "$target" "$skill_name"; then
    return
  fi
  if [ -e "$target" ]; then
    echo "unmanaged adapter collision: $target" >&2
    return 1
  fi
}

create_candidate() {
  local source="$1"
  local candidate="$2"
  local expected_link="$3"
  local skill_name="$4"
  local source_hash

  if [ -e "$candidate" ] || [ -L "$candidate" ]; then
    echo "temporary adapter collision: $candidate" >&2
    return 1
  fi
  if [ "$MODE" != "copy" ]; then
    if ln -s "$expected_link" "$candidate" 2>/dev/null; then
      return
    fi
    if [ "$MODE" = "symlink" ]; then
      echo "failed to create symlink adapter: $candidate" >&2
      return 1
    fi
  fi

  if ! cp -R "$source" "$candidate"; then
    rm -rf "$candidate"
    return 1
  fi
  if ! source_hash="$(hash_directory "$source")"; then
    rm -rf "$candidate"
    return 1
  fi
  if ! printf 'source=skills/%s\nhash=%s\n' \
    "$skill_name" "$source_hash" > "$candidate/$HASH_FILE"; then
    rm -rf "$candidate"
    return 1
  fi
}

validate_candidate() {
  local candidate="$1"
  local expected_link="$2"
  local skill_name="$3"

  if [ -L "$candidate" ]; then
    [ "$(readlink "$candidate")" = "$expected_link" ] && [ -f "$candidate/SKILL.md" ]
    return
  fi
  is_managed_copy "$candidate" "$skill_name"
}

activate_candidate() {
  local target="$1"
  local candidate="$2"
  local backup="$3"

  if [ ! -e "$target" ] && [ ! -L "$target" ]; then
    if mv "$candidate" "$target"; then
      return
    fi
    rm -rf "$candidate"
    return 1
  fi
  if [ -e "$backup" ] || [ -L "$backup" ]; then
    echo "temporary adapter collision: $backup" >&2
    rm -rf "$candidate"
    return 1
  fi
  if ! mv "$target" "$backup"; then
    rm -rf "$candidate"
    return 1
  fi
  if mv "$candidate" "$target"; then
    if ! rm -rf "$backup"; then
      echo "installed adapter but failed to remove retired backup: $backup" >&2
    fi
    return
  fi

  echo "failed to activate adapter; restoring previous adapter: $target" >&2
  if ! mv "$backup" "$target"; then
    echo "failed to restore previous adapter: $backup" >&2
    return 1
  fi
  if ! rm -rf "$candidate"; then
    echo "restored previous adapter but failed to remove candidate: $candidate" >&2
  fi
  return 1
}

install_adapter() {
  local source="$1"
  local adapter_root="$2"
  local skill_name
  local target
  local expected_link
  local candidate
  local backup

  skill_name="$(basename "$source")"
  target="$adapter_root/$skill_name"
  expected_link="$(relative_source "$skill_name")"
  candidate="$adapter_root/.$skill_name.adapter.$$"
  backup="$adapter_root/.$skill_name.backup.$$"
  validate_replaceable_target "$target" "$expected_link" "$skill_name"
  create_candidate "$source" "$candidate" "$expected_link" "$skill_name"
  if ! validate_candidate "$candidate" "$expected_link" "$skill_name"; then
    echo "invalid adapter candidate: $candidate" >&2
    rm -rf "$candidate"
    return 1
  fi
  activate_candidate "$target" "$candidate" "$backup"

  if [ -L "$target" ]; then
    echo "installed symlink adapter: ${target#"$ROOT/"}"
  else
    echo "installed copy adapter: ${target#"$ROOT/"}"
  fi
}

cleanup_stale_adapters() {
  local adapter_root="$1"
  local target
  local skill_name
  local expected_link

  for target in "$adapter_root"/*; do
    [ -e "$target" ] || [ -L "$target" ] || continue
    skill_name="$(basename "$target")"
    [ -f "$SOURCE_ROOT/$skill_name/SKILL.md" ] && continue
    expected_link="$(relative_source "$skill_name")"

    if [ -L "$target" ] && [ "$(readlink "$target")" = "$expected_link" ]; then
      rm "$target"
      echo "removed stale adapter: ${target#"$ROOT/"}"
    elif is_managed_copy "$target" "$skill_name"; then
      rm -rf "$target"
      echo "removed stale adapter: ${target#"$ROOT/"}"
    fi
  done
}

validate_adapter() {
  local source="$1"
  local adapter_root="$2"
  local skill_name
  local target
  local expected_link
  local expected_hash
  local recorded_hash
  local adapter_hash

  skill_name="$(basename "$source")"
  target="$adapter_root/$skill_name"
  expected_link="$(relative_source "$skill_name")"
  if [ -L "$target" ]; then
    if [ "$(readlink "$target")" != "$expected_link" ] || [ ! -f "$target/SKILL.md" ]; then
      echo "invalid symlink adapter: $target" >&2
      return 1
    fi
    return
  fi
  if ! has_managed_copy_metadata "$target" "$skill_name"; then
    echo "missing or unmanaged skill adapter: $target; run scripts/setup-dev-tools.sh" >&2
    return 1
  fi

  expected_hash="$(hash_directory "$source")"
  recorded_hash="$(sed -n 's/^hash=//p' "$target/$HASH_FILE")"
  if [ "$expected_hash" != "$recorded_hash" ]; then
    echo "skill adapter source drift: $target; run scripts/setup-dev-tools.sh" >&2
    return 1
  fi
  adapter_hash="$(hash_directory "$target")"
  if [ "$adapter_hash" != "$recorded_hash" ]; then
    echo "skill adapter content drift: $target; run scripts/setup-dev-tools.sh" >&2
    return 1
  fi
}

validate_no_stale_adapters() {
  local adapter_root="$1"
  local target
  local skill_name
  local expected_link
  local failed=0

  for target in "$adapter_root"/*; do
    [ -e "$target" ] || [ -L "$target" ] || continue
    skill_name="$(basename "$target")"
    [ -f "$SOURCE_ROOT/$skill_name/SKILL.md" ] && continue
    expected_link="$(relative_source "$skill_name")"
    if { [ -L "$target" ] && [ "$(readlink "$target")" = "$expected_link" ]; } ||
      is_managed_copy "$target" "$skill_name"; then
      echo "stale skill adapter: $target; run scripts/setup-dev-tools.sh" >&2
    else
      echo "unmanaged skill adapter: $target" >&2
    fi
    failed=1
  done

  return "$failed"
}
