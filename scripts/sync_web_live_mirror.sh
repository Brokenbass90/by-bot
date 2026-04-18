#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_IP="${SERVER_IP:-64.226.73.119}"
SERVER_USER="${SERVER_USER:-root}"
BOT_DIR="${BOT_DIR:-/root/by-bot}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/by-bot}"
MIRROR_ROOT="${MIRROR_ROOT:-$ROOT/runtime/live_mirror}"

SSH_OPTS=(-o StrictHostKeyChecking=no)
if [[ -n "${SSH_KEY:-}" && -f "${SSH_KEY}" ]]; then
  SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=no)
fi

mkdir -p "$MIRROR_ROOT"/regime "$MIRROR_ROOT"/control_plane "$MIRROR_ROOT"/operator "$MIRROR_ROOT"/equities_monthly_v36

copy_if_exists() {
  local remote_path="$1"
  local local_path="$2"
  local local_dir
  local_dir="$(dirname "$local_path")"
  mkdir -p "$local_dir"
  if ssh "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP" "test -f '$remote_path'"; then
    scp "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP:$remote_path" "$local_path" >/dev/null
    echo "[mirror] synced ${remote_path#$BOT_DIR/} -> ${local_path#$ROOT/}"
  else
    echo "[mirror] missing ${remote_path#$BOT_DIR/}"
  fi
}

copy_if_exists "$BOT_DIR/runtime/bot_heartbeat.json" "$MIRROR_ROOT/bot_heartbeat.json"
copy_if_exists "$BOT_DIR/runtime/regime/orchestrator_state.json" "$MIRROR_ROOT/regime/orchestrator_state.json"
copy_if_exists "$BOT_DIR/runtime/control_plane/portfolio_allocator_state.json" "$MIRROR_ROOT/control_plane/portfolio_allocator_state.json"
copy_if_exists "$BOT_DIR/runtime/control_plane/control_plane_watchdog_state.json" "$MIRROR_ROOT/control_plane/control_plane_watchdog_state.json"
copy_if_exists "$BOT_DIR/runtime/operator/operator_snapshot.json" "$MIRROR_ROOT/operator/operator_snapshot.json"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/current_cycle_picks.csv" "$MIRROR_ROOT/equities_monthly_v36/current_cycle_picks.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/latest_summary.csv" "$MIRROR_ROOT/equities_monthly_v36/latest_summary.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/latest_advisory.json" "$MIRROR_ROOT/equities_monthly_v36/latest_advisory.json"
copy_if_exists "$BOT_DIR/configs/intraday_state.json" "$MIRROR_ROOT/intraday_state.json"
copy_if_exists "$BOT_DIR/trades.csv" "$MIRROR_ROOT/trades.csv"

echo "[mirror] done root=$MIRROR_ROOT"
