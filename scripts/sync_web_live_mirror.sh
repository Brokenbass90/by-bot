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
BUNDLE_MANIFEST="$MIRROR_ROOT/sync_bundle_manifest.json"
SYNC_LOCK_DIR="$MIRROR_ROOT/.sync_lock"
SYNC_STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SYNCED_COUNT=0
MISSING_COUNT=0
FAILURES=()
CRITICAL_FAILURES=()

SSH_OPTS=(-o StrictHostKeyChecking=no)
if [[ -n "${SSH_KEY:-}" && -f "${SSH_KEY}" ]]; then
  SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=no)
fi

mkdir -p \
  "$MIRROR_ROOT"/regime \
  "$MIRROR_ROOT"/control_plane \
  "$MIRROR_ROOT"/operator \
  "$MIRROR_ROOT"/equities_monthly_v36 \
  "$MIRROR_ROOT"/alpaca_live_v38 \
  "$MIRROR_ROOT"/equities_monthly_v38_more_active_research \
  "$MIRROR_ROOT"/equities_intraday_dynamic_v1 \
  "$MIRROR_ROOT"/equities_intraday_dynamic_v3_shadow \
  "$MIRROR_ROOT"/ai_context \
  "$MIRROR_ROOT"/crypto_blocker \
  "$MIRROR_ROOT"/arb

# The web launcher starts an immediate sync and a periodic loop.  A slow SSH
# round-trip used to let both copies overlap, producing a mixed-generation
# mirror.  Use an atomic directory lock (portable to the macOS Bash 3.2 that
# runs the owner workstation) and recover only clearly stale locks.
if ! mkdir "$SYNC_LOCK_DIR" 2>/dev/null; then
  now_epoch="$(date +%s)"
  lock_mtime="$(stat -f %m "$SYNC_LOCK_DIR" 2>/dev/null || echo 0)"
  if [[ "$lock_mtime" =~ ^[0-9]+$ ]] && (( now_epoch - lock_mtime > 900 )); then
    rmdir "$SYNC_LOCK_DIR" 2>/dev/null || true
  fi
  if ! mkdir "$SYNC_LOCK_DIR" 2>/dev/null; then
    echo "[mirror] another sync is active; skipping overlapping run"
    exit 0
  fi
fi
trap 'rmdir "$SYNC_LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

write_bundle_manifest() {
  local status="$1"
  shift || true
  python3 - "$BUNDLE_MANIFEST" "$MIRROR_ROOT" "$status" "$SYNC_STARTED_UTC" "$SYNCED_COUNT" "$MISSING_COUNT" "$@" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

manifest = Path(sys.argv[1])
root = Path(sys.argv[2])
status = sys.argv[3]
started = sys.argv[4]
synced = int(sys.argv[5])
missing = int(sys.argv[6])
failures = list(sys.argv[7:])
critical = [
    "bot_heartbeat.json",
    "live_positions.json",
    "regime/orchestrator_state.json",
    "control_plane/portfolio_allocator_state.json",
    "operator/operator_snapshot.json",
    "ai_context/full_context.json",
]
files = {}
for rel in critical:
    path = root / rel
    try:
        stat = path.stat()
    except OSError:
        files[rel] = {"present": False, "mtime": None, "size_bytes": None}
    else:
        files[rel] = {
            "present": True,
            "mtime": int(stat.st_mtime),
            "size_bytes": int(stat.st_size),
        }
payload = {
    "schema_version": 1,
    "status": status,
    "sync_started_utc": started,
    "sync_finished_utc": datetime.now(timezone.utc).isoformat() if status != "syncing" else None,
    "source": "ssh_vps_runtime",
    "synced_count": synced,
    "missing_count": missing,
    "failures": failures,
    "critical_files": files,
}
manifest.parent.mkdir(parents=True, exist_ok=True)
tmp = manifest.with_name(f"{manifest.name}.sync.{os.getpid()}")
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(tmp, manifest)
PY
}

write_bundle_manifest "syncing"

copy_if_exists() {
  local remote_path="$1"
  local local_path="$2"
  local critical="${3:-optional}"
  local local_tmp="${local_path}.sync.$$"
  local local_dir
  local_dir="$(dirname "$local_path")"
  mkdir -p "$local_dir"
  if ssh "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP" "test -f '$remote_path'"; then
    # Preserve the source mtime: Web/AI freshness must not turn stale payloads
    # into fresh ones merely because the mirror copied them again.  Download to
    # a sibling temporary file and rename atomically so readers never observe a
    # partially written JSON/CSV payload.
    if ! scp -p "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP:$remote_path" "$local_tmp" >/dev/null; then
      rm -f "$local_tmp"
      FAILURES+=("scp_failed:${remote_path#$BOT_DIR/}")
      if [[ "$critical" == "critical" ]]; then
        CRITICAL_FAILURES+=("scp_failed:${remote_path#$BOT_DIR/}")
      fi
      return 0
    fi
    if ! /bin/mv -f "$local_tmp" "$local_path"; then
      rm -f "$local_tmp"
      FAILURES+=("replace_failed:${remote_path#$BOT_DIR/}")
      if [[ "$critical" == "critical" ]]; then
        CRITICAL_FAILURES+=("replace_failed:${remote_path#$BOT_DIR/}")
      fi
      return 0
    fi
    SYNCED_COUNT=$((SYNCED_COUNT + 1))
    echo "[mirror] synced ${remote_path#$BOT_DIR/} -> ${local_path#$ROOT/}"
  else
    local remote_rc=$?
    MISSING_COUNT=$((MISSING_COUNT + 1))
    if [[ "$remote_rc" -eq 1 ]]; then
      echo "[mirror] missing ${remote_path#$BOT_DIR/}"
      if [[ "$critical" == "critical" ]]; then
        CRITICAL_FAILURES+=("missing:${remote_path#$BOT_DIR/}")
      fi
    else
      echo "[mirror] transport failure rc=$remote_rc ${remote_path#$BOT_DIR/}"
      FAILURES+=("transport_${remote_rc}:${remote_path#$BOT_DIR/}")
      if [[ "$critical" == "critical" ]]; then
        CRITICAL_FAILURES+=("transport_${remote_rc}:${remote_path#$BOT_DIR/}")
      fi
    fi
  fi
  return 0
}

copy_if_exists "$BOT_DIR/runtime/bot_heartbeat.json" "$MIRROR_ROOT/bot_heartbeat.json" critical
copy_if_exists "$BOT_DIR/runtime/regime/orchestrator_state.json" "$MIRROR_ROOT/regime/orchestrator_state.json" critical
copy_if_exists "$BOT_DIR/runtime/control_plane/portfolio_allocator_state.json" "$MIRROR_ROOT/control_plane/portfolio_allocator_state.json" critical
copy_if_exists "$BOT_DIR/runtime/control_plane/control_plane_watchdog_state.json" "$MIRROR_ROOT/control_plane/control_plane_watchdog_state.json"
copy_if_exists "$BOT_DIR/runtime/operator/operator_snapshot.json" "$MIRROR_ROOT/operator/operator_snapshot.json" critical
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/current_cycle_picks.csv" "$MIRROR_ROOT/equities_monthly_v36/current_cycle_picks.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/latest_summary.csv" "$MIRROR_ROOT/equities_monthly_v36/latest_summary.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/latest_advisory.json" "$MIRROR_ROOT/equities_monthly_v36/latest_advisory.json"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/latest_refresh.env" "$MIRROR_ROOT/equities_monthly_v36/latest_refresh.env"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v36/latest_manager_receipt.json" "$MIRROR_ROOT/equities_monthly_v36/latest_manager_receipt.json"
copy_if_exists "$BOT_DIR/runtime/alpaca_live_v38/account_state.json" "$MIRROR_ROOT/alpaca_live_v38/account_state.json"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v38_more_active_research/current_cycle_picks.csv" "$MIRROR_ROOT/equities_monthly_v38_more_active_research/current_cycle_picks.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v38_more_active_research/current_cycle_summary.csv" "$MIRROR_ROOT/equities_monthly_v38_more_active_research/current_cycle_summary.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v38_more_active_research/latest_summary.csv" "$MIRROR_ROOT/equities_monthly_v38_more_active_research/latest_summary.csv"
copy_if_exists "$BOT_DIR/runtime/equities_monthly_v38_more_active_research/latest_refresh.env" "$MIRROR_ROOT/equities_monthly_v38_more_active_research/latest_refresh.env"
copy_if_exists "$BOT_DIR/configs/intraday_state.json" "$MIRROR_ROOT/intraday_state.json"
copy_if_exists "$BOT_DIR/runtime/equities_intraday_dynamic_v1/latest_advisory.json" "$MIRROR_ROOT/equities_intraday_dynamic_v1/latest_advisory.json"
copy_if_exists "$BOT_DIR/runtime/equities_intraday_dynamic_v3_shadow/latest_advisory.json" "$MIRROR_ROOT/equities_intraday_dynamic_v3_shadow/latest_advisory.json"
copy_if_exists "$BOT_DIR/configs/intraday_state_v3_shadow.json" "$MIRROR_ROOT/intraday_state_v3_shadow.json"
copy_if_exists "$BOT_DIR/runtime/live_trade_events.jsonl" "$MIRROR_ROOT/live_trade_events.jsonl"
copy_if_exists "$BOT_DIR/runtime/ai_context/full_context.json" "$MIRROR_ROOT/ai_context/full_context.json" critical
copy_if_exists "$BOT_DIR/runtime/ai_context/extras.json" "$MIRROR_ROOT/ai_context/extras.json"
copy_if_exists "$BOT_DIR/runtime/ai_context/ohlc_and_logs.json" "$MIRROR_ROOT/ai_context/ohlc_and_logs.json"
copy_if_exists "$BOT_DIR/runtime/ai_context/memory_lines.jsonl" "$MIRROR_ROOT/ai_context/memory_lines.jsonl"
copy_if_exists "$BOT_DIR/runtime/crypto_blocker/latest.json" "$MIRROR_ROOT/crypto_blocker/latest.json"
copy_if_exists "$BOT_DIR/runtime/crypto_blocker/latest.md" "$MIRROR_ROOT/crypto_blocker/latest.md"
copy_if_exists "$BOT_DIR/runtime/bybit_api_key_expiry_status.json" "$MIRROR_ROOT/bybit_api_key_expiry_status.json"
copy_if_exists "$BOT_DIR/runtime/live_positions.json" "$MIRROR_ROOT/live_positions.json" critical
copy_if_exists "$BOT_DIR/runtime/arb/exchange_account_status.json" "$MIRROR_ROOT/arb/exchange_account_status.json"
copy_if_exists "$BOT_DIR/runtime/arb/exchange_account_readonly_status.json" "$MIRROR_ROOT/arb/exchange_account_readonly_status.json"
copy_if_exists "$BOT_DIR/runtime/arb/dry_run/latest.json" "$MIRROR_ROOT/arb/dry_run/latest.json"
copy_if_exists "$BOT_DIR/runtime/arb_roi_estimate.json" "$MIRROR_ROOT/arb_roi_estimate.json"
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

if [[ "${#CRITICAL_FAILURES[@]}" -eq 0 ]]; then
  # Bash 3.2 + `set -u` treats expansion of an empty array as an unbound
  # variable.  Avoid expanding it at all on the clean-success path.
  if [[ "${#FAILURES[@]}" -eq 0 ]]; then
    write_bundle_manifest "complete"
  else
    write_bundle_manifest "complete" "${FAILURES[@]}"
  fi
else
  if [[ "${#FAILURES[@]}" -eq 0 ]]; then
    write_bundle_manifest "incomplete" "${CRITICAL_FAILURES[@]}"
  else
    write_bundle_manifest "incomplete" "${CRITICAL_FAILURES[@]}" "${FAILURES[@]}"
  fi
fi

if ! sync_chat_history "$CHAT_REMOTE_PATH" "$CHAT_LOCAL_PATH"; then
  echo "[mirror] chat history sync failed; live bundle status is unchanged"
fi

echo "[mirror] done root=$MIRROR_ROOT synced=$SYNCED_COUNT missing=$MISSING_COUNT critical_failures=${#CRITICAL_FAILURES[@]}"
