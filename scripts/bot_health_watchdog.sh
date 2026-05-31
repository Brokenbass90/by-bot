#!/usr/bin/env bash
# bot_health_watchdog.sh
# External watchdog: runs via cron every 2 minutes.
# Checks bot_heartbeat.json — if stale, sends Telegram alert and optionally
# restarts. Restarts are guarded by a lock + cooldown/window cap so a stale
# heartbeat cannot create an infinite restart loop.
#
# Install on server:
#   bash scripts/setup_watchdog_cron.sh
#
# Or manually add to crontab:
#   */2 * * * * /bin/bash /root/by-bot/scripts/bot_health_watchdog.sh >> /root/by-bot/runtime/watchdog.log 2>&1

set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
SERVICE_NAME="${SERVICE_NAME:-bybot}"
HEARTBEAT_FILE="$BOT_DIR/runtime/bot_heartbeat.json"
MAX_AGE_SEC="${WATCHDOG_MAX_AGE_SEC:-90}"        # alert if heartbeat > 90s old
ALERT_COOLDOWN_SEC="${WATCHDOG_COOLDOWN_SEC:-600}"  # don't spam — max 1 alert per 10 min
ALERT_STATE_FILE="$BOT_DIR/runtime/watchdog_alert_state.json"
AUTO_RESTART="${WATCHDOG_AUTO_RESTART:-0}"        # set to 1 to enable auto-restart via systemd
RESTART_STATE_FILE="$BOT_DIR/runtime/watchdog_restart_state.json"
RESTART_LOCK_DIR="$BOT_DIR/runtime/watchdog_restart.lock"
RESTART_COOLDOWN_SEC="${WATCHDOG_RESTART_COOLDOWN_SEC:-900}"  # max 1 restart per 15 min
RESTART_WINDOW_SEC="${WATCHDOG_RESTART_WINDOW_SEC:-3600}"      # rolling window for loop guard
RESTART_MAX_IN_WINDOW="${WATCHDOG_RESTART_MAX_IN_WINDOW:-3}"   # max restarts per window

TG_TOKEN="${TG_TOKEN:-}"
TG_CHAT="${TG_CHAT_ID:-${TG_CHAT:-}}"

if [[ -f "$BOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BOT_DIR/.env"
  set +a
  AUTO_RESTART="${WATCHDOG_AUTO_RESTART:-${AUTO_RESTART:-0}}"
  RESTART_COOLDOWN_SEC="${WATCHDOG_RESTART_COOLDOWN_SEC:-${RESTART_COOLDOWN_SEC:-900}}"
  RESTART_WINDOW_SEC="${WATCHDOG_RESTART_WINDOW_SEC:-${RESTART_WINDOW_SEC:-3600}}"
  RESTART_MAX_IN_WINDOW="${WATCHDOG_RESTART_MAX_IN_WINDOW:-${RESTART_MAX_IN_WINDOW:-3}}"
  TG_TOKEN="${TG_TOKEN:-}"
  TG_CHAT="${TG_CHAT_ID:-${TG_CHAT:-}}"
fi

NOW=$(date +%s)

# ── Guarded restart helper ────────────────────────────────────────
attempt_restart() {
  local reason="$1"
  if [[ "$AUTO_RESTART" != "1" ]]; then
    echo "[watchdog] Auto-restart disabled. reason=$reason"
    return
  fi

  mkdir -p "$BOT_DIR/runtime"
  if ! mkdir "$RESTART_LOCK_DIR" 2>/dev/null; then
    echo "[watchdog] Restart suppressed: another watchdog instance holds restart lock. reason=$reason"
    return
  fi

  local decision
  decision=$(python3 - "$RESTART_STATE_FILE" "$NOW" "$RESTART_WINDOW_SEC" "$RESTART_MAX_IN_WINDOW" "$RESTART_COOLDOWN_SEC" "$reason" <<'PY' || echo "deny|restart guard error"
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
now = int(sys.argv[2])
window = max(1, int(sys.argv[3]))
max_in_window = max(1, int(sys.argv[4]))
cooldown = max(0, int(sys.argv[5]))
reason = str(sys.argv[6])

try:
    data = json.loads(path.read_text())
except Exception:
    data = {}

raw = data.get("restarts") or []
events = []
for item in raw:
    if isinstance(item, dict):
        ts = int(item.get("ts", 0) or 0)
    else:
        ts = int(item or 0)
    if ts > 0 and now - ts <= window:
        events.append({"ts": ts, "reason": str((item or {}).get("reason", "")) if isinstance(item, dict) else ""})

last_ts = max([int(x.get("ts", 0) or 0) for x in events], default=0)
if last_ts and now - last_ts < cooldown:
    print(f"deny|cooldown active: last_restart_age={now - last_ts}s cooldown={cooldown}s recent={len(events)}/{max_in_window}")
    sys.exit(0)

if len(events) >= max_in_window:
    data.update(
        {
            "last_denied_ts": now,
            "last_denied_reason": reason,
            "deny_kind": "restart_loop_guard",
            "window_sec": window,
            "max_in_window": max_in_window,
            "restarts": events,
            "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        }
    )
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"deny|restart loop guard: recent={len(events)}/{max_in_window} window={window}s")
    sys.exit(0)

events.append({"ts": now, "reason": reason})
data.update(
    {
        "last_restart_ts": now,
        "last_restart_reason": reason,
        "window_sec": window,
        "max_in_window": max_in_window,
        "cooldown_sec": cooldown,
        "restarts": events,
        "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }
)
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
print(f"allow|recent={len(events)}/{max_in_window} window={window}s cooldown={cooldown}s")
PY
)

  local action="${decision%%|*}"
  local detail="${decision#*|}"
  if [[ "$action" != "allow" ]]; then
    echo "[watchdog] Restart suppressed: $detail reason=$reason"
    rmdir "$RESTART_LOCK_DIR" 2>/dev/null || true
    return
  fi

  echo "[watchdog] Restart allowed: $detail reason=$reason"
  if systemctl restart "$SERVICE_NAME"; then
    echo "[watchdog] Restart issued. reason=$reason"
  else
    echo "[watchdog] Restart FAILED. reason=$reason"
  fi
  rmdir "$RESTART_LOCK_DIR" 2>/dev/null || true
}

# ── Telegram send helper ──────────────────────────────────────────
send_tg() {
  local msg="$1"
  if [[ -z "$TG_TOKEN" || -z "$TG_CHAT" ]]; then
    echo "[watchdog] TG not configured, skipping alert"
    return
  fi
  curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    -d chat_id="$TG_CHAT" \
    -d text="$msg" \
    -d parse_mode="HTML" \
    --max-time 10 > /dev/null || true
}

# ── Cooldown check ────────────────────────────────────────────────
last_alert=0
if [[ -f "$ALERT_STATE_FILE" ]]; then
  last_alert=$(python3 -c "import json; d=json.load(open('$ALERT_STATE_FILE')); print(d.get('last_alert_ts',0))" 2>/dev/null || echo 0)
fi
cooldown_ok=$(( NOW - last_alert >= ALERT_COOLDOWN_SEC ))

# ── Check heartbeat file ──────────────────────────────────────────
if [[ ! -f "$HEARTBEAT_FILE" ]]; then
  echo "[watchdog $(date -u '+%H:%M:%S')] MISSING heartbeat file"
  if (( cooldown_ok )); then
    send_tg "🚨 <b>BOT DEAD</b>: heartbeat file missing entirely. Service=<b>${SERVICE_NAME}</b>. Bot likely never started or crashed badly."
    python3 -c "import json,time; json.dump({'last_alert_ts': int(time.time()), 'reason': 'missing_file'}, open('$ALERT_STATE_FILE','w'))" 2>/dev/null || true
  fi
  attempt_restart "missing_heartbeat_file"
  exit 0
fi

# Parse heartbeat
HB_TS=$(python3 -c "import json; d=json.load(open('$HEARTBEAT_FILE')); print(d.get('ts',0))" 2>/dev/null || echo 0)
AGE=$(( NOW - HB_TS ))

if (( AGE > MAX_AGE_SEC )); then
  echo "[watchdog $(date -u '+%H:%M:%S')] STALE heartbeat — age=${AGE}s (max=${MAX_AGE_SEC}s)"

  if (( cooldown_ok )); then
    # Get extra info from heartbeat
    INFO=$(python3 -c "
import json
d = json.load(open('$HEARTBEAT_FILE'))
print(f\"open_trades={d.get('open_trades','?')} ws_guard={d.get('ws_guard_active','?')} regime={d.get('regime','?')} uptime={d.get('uptime_s','?')}s\")
" 2>/dev/null || echo "parse error")
    if [[ "$AUTO_RESTART" == "1" ]]; then
      RESTART_NOTE="Auto-restart enabled with cooldown=${RESTART_COOLDOWN_SEC}s, max=${RESTART_MAX_IN_WINDOW}/${RESTART_WINDOW_SEC}s."
    else
      RESTART_NOTE="Manual restart needed: systemctl restart ${SERVICE_NAME}"
    fi
    send_tg "🚨 <b>BOT UNRESPONSIVE</b>: heartbeat is ${AGE}s old (limit=${MAX_AGE_SEC}s).
Last known state: ${INFO}
${RESTART_NOTE}"
    python3 -c "import json,time; json.dump({'last_alert_ts': int(time.time()), 'reason': 'stale', 'age_s': $AGE}, open('$ALERT_STATE_FILE','w'))" 2>/dev/null || true
  fi

  attempt_restart "stale_heartbeat_age_${AGE}s"
else
  echo "[watchdog $(date -u '+%H:%M:%S')] OK — heartbeat age=${AGE}s"
fi

# ── Router degraded_fallback auto-recovery ────────────────────────
# If router is in degraded_fallback, try to rebuild it (with retry logic).
# Cooldown: max 1 rebuild attempt per 30 minutes to avoid hammering the API.
ROUTER_STATE_FILE="$BOT_DIR/runtime/router/symbol_router_state.json"
ROUTER_REPAIR_STATE="$BOT_DIR/runtime/watchdog_router_repair_state.json"
ROUTER_REPAIR_COOLDOWN="${WATCHDOG_ROUTER_REPAIR_COOLDOWN_SEC:-1800}"  # 30 min

router_status=""
if [[ -f "$ROUTER_STATE_FILE" ]]; then
  router_status=$(python3 -c "
import json
try:
    d = json.load(open('$ROUTER_STATE_FILE'))
    print(d.get('status',''))
except Exception:
    print('')
" 2>/dev/null || echo "")
fi

if [[ "$router_status" == "degraded_fallback" ]]; then
  last_repair=0
  if [[ -f "$ROUTER_REPAIR_STATE" ]]; then
    last_repair=$(python3 -c "import json; d=json.load(open('$ROUTER_REPAIR_STATE')); print(d.get('last_repair_ts',0))" 2>/dev/null || echo 0)
  fi
  repair_ok=$(( NOW - last_repair >= ROUTER_REPAIR_COOLDOWN ))

  if (( repair_ok )); then
    echo "[watchdog $(date -u '+%H:%M:%S')] Router DEGRADED — attempting auto-repair..."
    cd "$BOT_DIR"
    if [[ -f ".venv/bin/activate" ]]; then source .venv/bin/activate; fi

    # Run with retry (3 attempts, 30s each — built into build_symbol_router.py)
    python3 scripts/build_symbol_router.py --quiet \
      --scan-retries 3 --scan-retry-delay-sec 30 \
      >> "$BOT_DIR/runtime/watchdog_router_repair.log" 2>&1
    RC=$?

    python3 -c "import json,time; json.dump({'last_repair_ts': int(time.time()), 'rc': $RC}, open('$ROUTER_REPAIR_STATE','w'))" 2>/dev/null || true

    if [[ $RC -eq 0 ]]; then
      echo "[watchdog] Router repair OK"
      if (( cooldown_ok )); then
        send_tg "✅ <b>Router recovered</b>: degraded_fallback → ok after auto-repair."
      fi
    else
      echo "[watchdog] Router repair FAILED (rc=$RC) — will retry in ${ROUTER_REPAIR_COOLDOWN}s"
      if (( cooldown_ok )); then
        send_tg "⚠️ <b>Router still degraded</b>: auto-repair attempt failed. Check logs: runtime/watchdog_router_repair.log"
      fi
    fi
  else
    echo "[watchdog $(date -u '+%H:%M:%S')] Router degraded but repair cooldown active ($(( NOW - last_repair ))s ago)"
  fi
else
  echo "[watchdog $(date -u '+%H:%M:%S')] Router status=${router_status:-unknown}"
fi
