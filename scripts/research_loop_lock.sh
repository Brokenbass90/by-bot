#!/usr/bin/env bash
# Shared crash-safe single-instance lock for long-running risk-zero loops.
# A directory lock survives a hard shutdown, so every owner PID is recorded and
# a later boot may recover the lock only after proving that PID is no longer alive.

acquire_research_loop_lock() {
  local lock_dir="${1:?lock directory is required}"
  local owner_pid=""

  mkdir -p "$(dirname "$lock_dir")"
  if ! mkdir "$lock_dir" 2>/dev/null; then
    if [[ -r "$lock_dir/pid" ]]; then
      read -r owner_pid < "$lock_dir/pid" || true
    fi
    if [[ -n "$owner_pid" ]] && kill -0 "$owner_pid" 2>/dev/null; then
      echo "research loop already running: $lock_dir (pid=$owner_pid)"
      return 1
    fi
    rm -f "$lock_dir/pid"
    if ! rmdir "$lock_dir" 2>/dev/null || ! mkdir "$lock_dir" 2>/dev/null; then
      echo "cannot recover stale research loop lock: $lock_dir" >&2
      return 1
    fi
  fi

  printf '%s\n' "$$" > "$lock_dir/pid"
  RESEARCH_LOOP_LOCK_DIR="$lock_dir"
  trap 'rm -f "${RESEARCH_LOOP_LOCK_DIR}/pid"; rmdir "${RESEARCH_LOOP_LOCK_DIR}" 2>/dev/null || true' EXIT INT TERM HUP
  return 0
}
