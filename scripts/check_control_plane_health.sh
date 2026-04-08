#!/usr/bin/env bash
# check_control_plane_health.sh
# Verifies that the control-plane files (regime state, router, allocator) are fresh.
# Sends a Telegram alert if any file is stale or missing.
#
# Run via cron (e.g. every 30 minutes):
#   */30 * * * * /bin/bash /root/by-bot/scripts/check_control_plane_health.sh >> /root/by-bot/runtime/cp_health.log 2>&1
#
# Or add to setup_watchdog_cron.sh for combined installation.
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
NOW=$(date +%s)
PROBLEMS=()

TG_TOKEN="${TG_TOKEN:-}"
TG_CHAT="${TG_CHAT_ID:-${TG_CHAT:-}}"

# Max allowed ages (seconds)
REGIME_MAX_AGE="${CP_REGIME_MAX_AGE_SEC:-7200}"         # 2 hours — runs hourly
ROUTER_MAX_AGE="${CP_ROUTER_MAX_AGE_SEC:-28800}"        # 8 hours — router now every 6h
ALLOCATOR_MAX_AGE="${CP_ALLOCATOR_MAX_AGE_SEC:-10800}"  # 3 hours — runs hourly

send_tg() {
  local msg="$1"
  [[ -z "$TG_TOKEN" || -z "$TG_CHAT" ]] && { echo "[cp_health] TG not configured"; return; }
  curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    -d chat_id="$TG_CHAT" \
    -d text="$msg" \
    -d parse_mode="HTML" \
    --max-time 10 > /dev/null || true
}

check_file() {
  local label="$1"
  local filepath="$2"
  local max_age="$3"
  local ts_field="${4:-timestamp_utc}"  # JSON field name for timestamp

  if [[ ! -f "$filepath" ]]; then
    PROBLEMS+=("❌ $label: FILE MISSING ($filepath)")
    return
  fi

  # Get modification time of file
  FILE_MTIME=$(stat -c "%Y" "$filepath" 2>/dev/null || stat -f "%m" "$filepath" 2>/dev/null || echo 0)
  AGE=$(( NOW - FILE_MTIME ))

  if (( AGE > max_age )); then
    PROBLEMS+=("⚠️ $label: STALE (age=${AGE}s, max=${max_age}s)")
  else
    echo "[cp_health $(date -u '+%H:%M:%S')] OK $label — age=${AGE}s"
  fi
}

# ── Check each control-plane file ────────────────────────────────
check_file \
  "Regime state" \
  "$BOT_DIR/runtime/regime/orchestrator_state.json" \
  "$REGIME_MAX_AGE"

check_file \
  "Symbol router" \
  "$BOT_DIR/runtime/router/symbol_router_state.json" \
  "$ROUTER_MAX_AGE"

check_file \
  "Portfolio allocator" \
  "$BOT_DIR/runtime/control_plane/portfolio_allocator_state.json" \
  "$ALLOCATOR_MAX_AGE"

# Also check the dynamic allowlist env (router output consumed by bot)
check_file \
  "Dynamic allowlist env" \
  "$BOT_DIR/configs/dynamic_allowlist_latest.env" \
  "$ROUTER_MAX_AGE"

check_file \
  "Regime overlay env" \
  "$BOT_DIR/configs/regime_orchestrator_latest.env" \
  "$REGIME_MAX_AGE"

check_file \
  "Allocator overlay env" \
  "$BOT_DIR/configs/portfolio_allocator_latest.env" \
  "$ALLOCATOR_MAX_AGE"

# ── Report results ────────────────────────────────────────────────
if (( ${#PROBLEMS[@]} > 0 )); then
  echo "[cp_health $(date -u '+%H:%M:%S')] PROBLEMS FOUND:"
  for p in "${PROBLEMS[@]}"; do
    echo "  $p"
  done

  # Check cooldown (don't spam)
  COOLDOWN_FILE="$BOT_DIR/runtime/cp_health_alert_ts.txt"
  LAST_ALERT=0
  [[ -f "$COOLDOWN_FILE" ]] && LAST_ALERT=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
  COOLDOWN="${CP_ALERT_COOLDOWN_SEC:-1800}"

  if (( NOW - LAST_ALERT >= COOLDOWN )); then
    MSG="⚙️ <b>Control-plane health issues:</b>
$(printf '%s\n' "${PROBLEMS[@]}")

Control-plane may not be running on schedule.
Check cron: crontab -l | egrep 'build_regime_state|build_symbol_router|build_portfolio_allocator|control_plane_watchdog'"
    send_tg "$MSG"
    echo "$NOW" > "$COOLDOWN_FILE"
  fi
else
  echo "[cp_health $(date -u '+%H:%M:%S')] All control-plane files OK"
fi
