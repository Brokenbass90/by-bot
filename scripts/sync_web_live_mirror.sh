#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_IP="${SERVER_IP:-64.226.73.119}"
SERVER_USER="${SERVER_USER:-root}"
BOT_DIR="${BOT_DIR:-/root/by-bot}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/by-bot}"
MIRROR_ROOT="${MIRROR_ROOT:-$ROOT/runtime/live_mirror}"
CHAT_REMOTE_PATH="${CHAT_REMOTE_PATH:-$BOT_DIR/data/deepseek_chat.json}"
CHAT_LOCAL_PATH="${CHAT_LOCAL_PATH:-$MIRROR_ROOT/deepseek_chat.json}"
CHAT_HISTORY_MAX="${DEEPSEEK_HISTORY_MAX_MESSAGES:-15}"

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
copy_if_exists "$BOT_DIR/runtime/live_trade_events.jsonl" "$MIRROR_ROOT/live_trade_events.jsonl"
copy_if_exists "$BOT_DIR/trades.csv" "$MIRROR_ROOT/trades.csv"

sync_chat_history() {
  local remote_path="$1"
  local local_path="$2"
  local remote_tmp="${local_path}.remote"
  local local_dir
  local_dir="$(dirname "$local_path")"
  mkdir -p "$local_dir"

  if ssh "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP" "test -f '$remote_path'"; then
    scp "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP:$remote_path" "$remote_tmp" >/dev/null
  else
    printf '[]\n' > "$remote_tmp"
  fi

  python3 - "$local_path" "$remote_tmp" "$CHAT_HISTORY_MAX" <<'PY'
import json, sys
from pathlib import Path

local_path = Path(sys.argv[1])
remote_tmp = Path(sys.argv[2])
max_items = max(1, int(sys.argv[3] or "15"))

def load(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("messages", [])
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            out.append({"role": role, "content": content})
    return out

merged = []
for item in load(remote_tmp) + load(local_path):
    if merged and merged[-1] == item:
        continue
    merged.append(item)
merged = merged[-max_items:]
local_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
PY

  if [[ -f "$local_path" ]]; then
    scp "${SSH_OPTS[@]}" "$local_path" "$SERVER_USER@$SERVER_IP:$remote_path" >/dev/null
    echo "[mirror] synced chat history -> ${local_path#$ROOT/}"
  fi
  rm -f "$remote_tmp"
}

sync_chat_history "$CHAT_REMOTE_PATH" "$CHAT_LOCAL_PATH"

echo "[mirror] done root=$MIRROR_ROOT"
