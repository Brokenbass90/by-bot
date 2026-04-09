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
SCHEDULE_PROBLEMS=()
STATE_PROBLEMS=()
STATE_FILE="$BOT_DIR/runtime/cp_health_alert_state.json"

TG_TOKEN="${TG_TOKEN:-}"
TG_CHAT="${TG_CHAT_ID:-${TG_CHAT:-}}"

if [[ -f "$BOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BOT_DIR/.env"
  set +a
  TG_TOKEN="${TG_TOKEN:-}"
  TG_CHAT="${TG_CHAT_ID:-${TG_CHAT:-}}"
fi

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

json_state_get() {
  local field="$1"
  python3 - <<'PY' "$STATE_FILE" "$field" 2>/dev/null || true
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
field = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
value = data.get(field, "")
if isinstance(value, bool):
    print("1" if value else "0")
elif value is None:
    print("")
else:
    print(value)
PY
}

json_state_write() {
  local active="$1"
  local fingerprint="$2"
  local count="$3"
  local first_seen="$4"
  local last_seen="$5"
  local last_sent="$6"
  local status="$7"
  local note="$8"
  python3 - <<'PY' "$STATE_FILE" "$active" "$fingerprint" "$count" "$first_seen" "$last_seen" "$last_sent" "$status" "$note"
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
payload = {
    "active": sys.argv[2] == "1",
    "fingerprint": sys.argv[3],
    "count": int(sys.argv[4] or 0),
    "first_seen": int(sys.argv[5] or 0),
    "last_seen": int(sys.argv[6] or 0),
    "last_sent": int(sys.argv[7] or 0),
    "status": sys.argv[8],
    "note": sys.argv[9],
}
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
tmp.replace(path)
PY
}

make_fingerprint() {
  python3 - <<'PY' "$@"
import hashlib, sys
parts = sys.argv[1:]
joined = "\n".join(p for p in parts if p)
print(hashlib.sha1(joined.encode("utf-8")).hexdigest())
PY
}

format_utc_ts() {
  local ts="$1"
  python3 - <<'PY' "$ts" 2>/dev/null || true
from datetime import datetime, timezone
import sys
try:
    ts = int(sys.argv[1] or 0)
except Exception:
    ts = 0
if ts > 0:
    print(datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
PY
}

check_file() {
  local label="$1"
  local filepath="$2"
  local max_age="$3"
  local ts_field="${4:-timestamp_utc}"  # JSON field name for timestamp

  if [[ ! -f "$filepath" ]]; then
    PROBLEMS+=("❌ $label: FILE MISSING ($filepath)")
    SCHEDULE_PROBLEMS+=("$label missing")
    return
  fi

  # Get modification time of file
  FILE_MTIME=$(stat -c "%Y" "$filepath" 2>/dev/null || stat -f "%m" "$filepath" 2>/dev/null || echo 0)
  AGE=$(( NOW - FILE_MTIME ))

  if (( AGE > max_age )); then
    PROBLEMS+=("⚠️ $label: STALE (age=${AGE}s, max=${max_age}s)")
    SCHEDULE_PROBLEMS+=("$label stale age=${AGE}s")
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

check_router_content() {
  local filepath="$1"
  [[ ! -f "$filepath" ]] && return

  local router_meta
  router_meta=$(python3 - <<'PY' "$filepath" 2>/dev/null || true
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    print("parse_error")
    raise SystemExit(0)
status = str(data.get("status") or "")
scan_ok = bool(data.get("scan_ok", True))
fallback_count = len(list(data.get("fallback_reasons") or []))
print(f"{status}|{int(scan_ok)}|{fallback_count}")
PY
)

  if [[ -z "$router_meta" ]]; then
    PROBLEMS+=("⚠️ Symbol router: PARSE ERROR ($filepath)")
    return
  fi
  if [[ "$router_meta" == "parse_error" ]]; then
    PROBLEMS+=("⚠️ Symbol router: PARSE ERROR ($filepath)")
    return
  fi

  IFS='|' read -r ROUTER_STATUS ROUTER_SCAN_OK ROUTER_FALLBACKS <<< "$router_meta"
  if [[ "$ROUTER_STATUS" != "ok" || "$ROUTER_SCAN_OK" != "1" ]]; then
    PROBLEMS+=("⚠️ Symbol router: DEGRADED (status=${ROUTER_STATUS:-?}, scan_ok=${ROUTER_SCAN_OK:-?}, fallbacks=${ROUTER_FALLBACKS:-0})")
    STATE_PROBLEMS+=("router degraded status=${ROUTER_STATUS:-?} scan_ok=${ROUTER_SCAN_OK:-?} fallbacks=${ROUTER_FALLBACKS:-0}")
  fi
}

check_allocator_content() {
  local filepath="$1"
  [[ ! -f "$filepath" ]] && return

  local allocator_meta
  allocator_meta=$(python3 - <<'PY' "$filepath" 2>/dev/null || true
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    print("parse_error")
    raise SystemExit(0)
status = str(data.get("status") or "")
safe_mode = bool(data.get("safe_mode", False))
degraded = bool(data.get("degraded", False))
reasons = list(data.get("degraded_reasons") or [])
safe_reasons = list(data.get("safe_mode_reasons") or [])
reason_text = ";".join(str(x) for x in (reasons[:3] + safe_reasons[:3]))
print(f"{status}|{int(safe_mode)}|{int(degraded)}|{reason_text}")
PY
)

  if [[ -z "$allocator_meta" ]]; then
    PROBLEMS+=("⚠️ Portfolio allocator: PARSE ERROR ($filepath)")
    return
  fi
  if [[ "$allocator_meta" == "parse_error" ]]; then
    PROBLEMS+=("⚠️ Portfolio allocator: PARSE ERROR ($filepath)")
    return
  fi

  IFS='|' read -r ALLOC_STATUS ALLOC_SAFE ALLOC_DEGRADED ALLOC_REASON_TEXT <<< "$allocator_meta"
  local alloc_reason_lower="${ALLOC_REASON_TEXT,,}"
  local overlap_only=0
  if [[ "$ALLOC_SAFE" != "1" && "$ALLOC_DEGRADED" == "1" && "$ALLOC_STATUS" == "degraded" ]]; then
    if [[ -n "${alloc_reason_lower:-}" ]]; then
      overlap_only=1
      IFS=';' read -r -a _alloc_reason_parts <<< "$alloc_reason_lower"
      for _reason in "${_alloc_reason_parts[@]}"; do
        _reason="${_reason// /}"
        [[ -z "$_reason" ]] && continue
        if [[ "$_reason" != portfolio_overlap:* ]]; then
          overlap_only=0
          break
        fi
      done
    fi
  fi
  if (( overlap_only == 1 )); then
    echo "[cp_health $(date -u '+%H:%M:%S')] INFO allocator overlap-only degraded (${ALLOC_REASON_TEXT:-unknown})"
    return
  fi
  if [[ "$ALLOC_SAFE" == "1" || "$ALLOC_DEGRADED" == "1" || "$ALLOC_STATUS" != "ok" ]]; then
    local msg="⚠️ Portfolio allocator: DEGRADED (status=${ALLOC_STATUS:-?}, safe_mode=${ALLOC_SAFE:-0}, degraded=${ALLOC_DEGRADED:-0}"
    if [[ -n "${ALLOC_REASON_TEXT:-}" ]]; then
      msg="$msg, reason=${ALLOC_REASON_TEXT}"
    fi
    msg="$msg)"
    PROBLEMS+=("$msg")
    STATE_PROBLEMS+=("allocator degraded status=${ALLOC_STATUS:-?} reason=${ALLOC_REASON_TEXT:-unknown}")
  fi
}

check_router_content "$BOT_DIR/runtime/router/symbol_router_state.json"
check_allocator_content "$BOT_DIR/runtime/control_plane/portfolio_allocator_state.json"

# ── Report results ────────────────────────────────────────────────
if (( ${#PROBLEMS[@]} > 0 )); then
  echo "[cp_health $(date -u '+%H:%M:%S')] PROBLEMS FOUND:"
  for p in "${PROBLEMS[@]}"; do
    echo "  $p"
  done

  FINGERPRINT="$(make_fingerprint "$(printf '%s\n' "${PROBLEMS[@]}")" "$(printf '%s\n' "${SCHEDULE_PROBLEMS[@]}")" "$(printf '%s\n' "${STATE_PROBLEMS[@]}")")"
  PREV_ACTIVE="$(json_state_get active)"
  PREV_FINGERPRINT="$(json_state_get fingerprint)"
  PREV_COUNT="$(json_state_get count)"
  PREV_FIRST_SEEN="$(json_state_get first_seen)"
  PREV_LAST_SENT="$(json_state_get last_sent)"
  REPEAT_SEC="${CP_ALERT_REPEAT_SEC:-43200}"
  SEND_RECOVERY="${CP_ALERT_SEND_RECOVERY:-1}"

  if [[ -z "$PREV_COUNT" ]]; then PREV_COUNT=0; fi
  if [[ -z "$PREV_FIRST_SEEN" ]]; then PREV_FIRST_SEEN=$NOW; fi
  if [[ -z "$PREV_LAST_SENT" ]]; then PREV_LAST_SENT=0; fi

  COUNT=1
  FIRST_SEEN="$NOW"
  LAST_SENT="$PREV_LAST_SENT"
  SEND_NOW=0
  SEND_KIND="new"

  if [[ "$PREV_ACTIVE" == "1" && "$PREV_FINGERPRINT" == "$FINGERPRINT" ]]; then
    COUNT=$(( PREV_COUNT + 1 ))
    FIRST_SEEN="$PREV_FIRST_SEEN"
    if (( NOW - PREV_LAST_SENT >= REPEAT_SEC )); then
      SEND_NOW=1
      SEND_KIND="repeat"
      LAST_SENT="$NOW"
    fi
  else
    SEND_NOW=1
    SEND_KIND="new"
    LAST_SENT="$NOW"
  fi

  if (( SEND_NOW == 1 )); then
    MSG=$'⚙️ <b>Control-plane health issues:</b>\n'
    MSG+="$(printf '%s\n' "${PROBLEMS[@]}")"
    if [[ "$SEND_KIND" == "repeat" ]]; then
      FIRST_SEEN_TXT="$(format_utc_ts "$FIRST_SEEN")"
      if [[ -z "$FIRST_SEEN_TXT" ]]; then
        FIRST_SEEN_TXT="unknown start"
      fi
      MSG+=$'\n\n'
      MSG+="Repeat count: ${COUNT} identical occurrences since ${FIRST_SEEN_TXT}."
    fi
    if (( ${#SCHEDULE_PROBLEMS[@]} > 0 )); then
      MSG+=$'\n\n'
      MSG+="Likely scheduler / cron freshness issue."
      MSG+=$'\n'
      MSG+="Check cron: crontab -l | egrep 'build_regime_state|build_symbol_router|build_portfolio_allocator|control_plane_watchdog'"
    else
      MSG+=$'\n\n'
      MSG+="Schedule looks fresh; issue is in live control-plane state, not missing cron."
      MSG+=$'\n'
      MSG+="Check allocator/router reasons in:"
      MSG+=$'\n'
      MSG+="$BOT_DIR/runtime/control_plane/portfolio_allocator_state.json"
      MSG+=$'\n'
      MSG+="$BOT_DIR/runtime/router/symbol_router_state.json"
    fi
    send_tg "$MSG"
  else
    echo "[cp_health $(date -u '+%H:%M:%S')] duplicate issue suppressed count=$COUNT fingerprint=$FINGERPRINT"
  fi

  json_state_write "1" "$FINGERPRINT" "$COUNT" "$FIRST_SEEN" "$NOW" "$LAST_SENT" "problem" "$(printf '%s | ' "${PROBLEMS[@]}")"
else
  echo "[cp_health $(date -u '+%H:%M:%S')] All control-plane files OK"
  PREV_ACTIVE="$(json_state_get active)"
  PREV_COUNT="$(json_state_get count)"
  PREV_FIRST_SEEN="$(json_state_get first_seen)"
  PREV_LAST_SENT="$(json_state_get last_sent)"
  SEND_RECOVERY="${CP_ALERT_SEND_RECOVERY:-1}"
  if [[ "$PREV_ACTIVE" == "1" ]]; then
    if [[ "$SEND_RECOVERY" == "1" && -n "$PREV_LAST_SENT" && "$PREV_LAST_SENT" != "0" ]]; then
      DURATION=$(( NOW - ${PREV_FIRST_SEEN:-NOW} ))
      MSG=$'✅ <b>Control-plane recovered</b>\n\n'
      MSG+="The previous issue is no longer active."
      MSG+=$'\n'
      MSG+="Occurrences: ${PREV_COUNT:-1}"
      MSG+=$'\n'
      MSG+="Duration: ${DURATION}s"
      send_tg "$MSG"
    fi
    json_state_write "0" "" "0" "0" "$NOW" "${PREV_LAST_SENT:-0}" "ok" "resolved"
  fi
fi
