#!/usr/bin/env bash
# server_status.sh
# Показывает полный статус бота и control plane на сервере.
# Запускать ЛОКАЛЬНО:
#   SERVER_IP=64.226.73.119 bash scripts/server_status.sh
#
# Или на самом сервере:
#   bash /root/by-bot/scripts/server_status.sh --local
set -euo pipefail

SERVER_IP="${SERVER_IP:-64.226.73.119}"
SERVER_USER="${SERVER_USER:-root}"
BOT_DIR="${BOT_DIR:-/root/by-bot}"
SERVICE_NAME="${SERVICE_NAME:-bybot}"
LOCAL_MODE="${1:-}"
SSH_KEY="${SSH_KEY:-}"
DEFAULT_KEY="$HOME/.ssh/by-bot"

if [[ -z "$SSH_KEY" && -f "$DEFAULT_KEY" ]]; then
  SSH_KEY="$DEFAULT_KEY"
fi

if [[ -n "$SSH_KEY" ]]; then
  SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP"
else
  SSH_CMD="ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP"
fi
[[ "$LOCAL_MODE" == "--local" ]] && SSH_CMD="bash"

run() {
  if [[ "$LOCAL_MODE" == "--local" ]]; then
    bash -c "$1" 2>/dev/null || true
  else
    $SSH_CMD "$1" 2>/dev/null || true
  fi
}

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  BOT STATUS REPORT  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "═══════════════════════════════════════════════════════"

# ── 1. Bot process ────────────────────────────────────────────────
echo ""
echo "▶ BOT PROCESS"
run "systemctl is-active $SERVICE_NAME 2>/dev/null && echo '  ✅ systemd: RUNNING' || (screen -list 2>/dev/null | grep -q '\.bot' && echo '  ⚠️  screen: RUNNING (not systemd)' || echo '  ❌ NOT RUNNING')"
run "pgrep -fal 'python3 smart_pump_reversal_bot' 2>/dev/null | head -3 | sed 's/^/  PID: /' || echo '  (no python process found)'"

# ── 2. Heartbeat ──────────────────────────────────────────────────
echo ""
echo "▶ HEARTBEAT"
run "
HB=$BOT_DIR/runtime/bot_heartbeat.json
if [ -f \"\$HB\" ]; then
  NOW=\$(date +%s)
  TS=\$(python3 -c \"import json; print(json.load(open('\$HB')).get('ts',0))\" 2>/dev/null || echo 0)
  AGE=\$((NOW - TS))
  UPTIME=\$(python3 -c \"import json; s=json.load(open('\$HB')).get('uptime_s',0); h=s//3600; m=(s%3600)//60; print(f'{h}h{m:02d}m')\" 2>/dev/null || echo '?')
  TRADES=\$(python3 -c \"import json; print(json.load(open('\$HB')).get('open_trades','?'))\" 2>/dev/null || echo '?')
  WS=\$(python3 -c \"import json; print(json.load(open('\$HB')).get('ws_guard_active','?'))\" 2>/dev/null || echo '?')
  REGIME=\$(python3 -c \"import json; print(json.load(open('\$HB')).get('regime','?'))\" 2>/dev/null || echo '?')
  if [ \"\$AGE\" -lt 30 ]; then STATUS='✅ FRESH'; elif [ \"\$AGE\" -lt 90 ]; then STATUS='⚠️ WARN'; else STATUS='❌ STALE'; fi
  echo \"  \$STATUS  age=\${AGE}s  uptime=\$UPTIME  open_trades=\$TRADES  ws_guard=\$WS  regime=\$REGIME\"
else
  echo '  ❌ heartbeat file missing (bot never wrote it or old version)'
fi
"

# ── 3. Control plane files ────────────────────────────────────────
echo ""
echo "▶ CONTROL PLANE FILES"
run "
NOW=\$(date +%s)
check() {
  LABEL=\$1; FILE=\$2; MAX=\$3
  if [ -f \"\$FILE\" ]; then
    MTIME=\$(stat -c '%Y' \"\$FILE\" 2>/dev/null || stat -f '%m' \"\$FILE\" 2>/dev/null || echo 0)
    AGE=\$((NOW - MTIME))
    if [ \"\$AGE\" -lt \"\$MAX\" ]; then STATUS='✅'; else STATUS='❌ STALE'; fi
    echo \"  \$STATUS \$LABEL: age=\${AGE}s (max=\${MAX}s)\"
  else
    echo \"  ❌ MISSING \$LABEL\"
  fi
}
check 'Regime state       ' $BOT_DIR/runtime/regime/orchestrator_state.json 7200
check 'Regime overlay env ' $BOT_DIR/configs/regime_orchestrator_latest.env 7200
check 'Router state       ' $BOT_DIR/runtime/router/symbol_router_state.json 28800
check 'Allowlist env      ' $BOT_DIR/configs/dynamic_allowlist_latest.env 28800
check 'Allocator state    ' $BOT_DIR/runtime/control_plane/portfolio_allocator_state.json 10800
check 'Allocator env      ' $BOT_DIR/configs/portfolio_allocator_latest.env 10800
"

echo ""
echo "▶ ROUTER / ALLOCATOR QUALITY"
run "
ROUTER=$BOT_DIR/runtime/router/symbol_router_state.json
ALLOC=$BOT_DIR/runtime/control_plane/portfolio_allocator_state.json
if [ -f \"\$ROUTER\" ]; then
  python3 -c \"
import json
d = json.load(open('\$ROUTER'))
fallbacks = list(d.get('fallback_reasons') or [])
print(f\\\"  router_status={d.get('status','?')}  scan_ok={int(bool(d.get('scan_ok', True)))}  fallbacks={len(fallbacks)}\\\")
print(f\\\"  router_backtest_gate={'on' if d.get('backtest_path') else 'off'}  symbol_memory_loaded={int(bool(d.get('symbol_memory_loaded', False)))}\\\")
if fallbacks:
    preview = '; '.join(fallbacks[:3])
    print(f\\\"  router_fallback_preview={preview}\\\")
\" 2>/dev/null || echo '  router: parse error'
else
  echo '  router: missing'
fi
if [ -f \"\$ALLOC\" ]; then
  python3 -c \"
import json
d = json.load(open('\$ALLOC'))
global_risk = d.get('allocator_global_risk_mult', d.get('global_risk_mult', '?'))
print(f\\\"  allocator_status={d.get('status','?')}  degraded={int(bool(d.get('degraded', False)))}  safe_mode={int(bool(d.get('safe_mode', False)))}  global_risk={global_risk}\\\")
\" 2>/dev/null || echo '  allocator: parse error'
else
  echo '  allocator: missing'
fi
"

echo ""
echo "▶ NIGHTLY RESEARCH"
run "
NR=$BOT_DIR/runtime/research_nightly/status.json
if [ -f \"\$NR\" ]; then
  python3 -c \"
import json
d = json.load(open('\$NR'))
tasks = d.get('tasks') or {}
counts = {}
for item in tasks.values():
    state = str((item or {}).get('state') or 'unknown')
    counts[state] = counts.get(state, 0) + 1
print(f\\\"  state={d.get('state','?')} active_process_count={d.get('active_process_count','?')} launched={len(d.get('launched') or [])} proposed={len(d.get('proposed') or [])}\\\")
print(f\\\"  task_state_counts={counts}\\\")
\" 2>/dev/null || echo '  nightly research: parse error'
else
  echo '  nightly research: not configured yet'
fi
"

# ── 4. Current regime ─────────────────────────────────────────────
echo ""
echo "▶ CURRENT REGIME"
run "
FILE=$BOT_DIR/runtime/regime/orchestrator_state.json
if [ -f \"\$FILE\" ]; then
  python3 -c \"
import json
d = json.load(open('\$FILE'))
print(f\\\"  regime={d.get('regime','?')}  confidence={d.get('confidence','?'):.3f}  btc_bias={d.get('btc_bias','?')}  risk_level={d.get('risk_level','?')}\\\")
print(f\\\"  raw_regime={d.get('raw_regime','?')}  pending={d.get('pending_regime','?')} ({d.get('pending_count','?')}/3)\\\")
print(f\\\"  updated={d.get('timestamp_utc','?')}\\\")
\" 2>/dev/null || echo '  (parse error)'
else
  echo '  ❌ No regime state file'
fi
"

# ── 5. Active crons ───────────────────────────────────────────────
echo ""
echo "▶ CRONS"
run "crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | sed 's/^/  /' || echo '  (no crons or error)'"

# ── 6. Recent log tail ────────────────────────────────────────────
echo ""
echo "▶ RECENT BOT LOG (last 8 lines)"
run "tail -8 $BOT_DIR/runtime/live.out 2>/dev/null | sed 's/^/  /' || journalctl -u $SERVICE_NAME -n 8 --no-pager 2>/dev/null | sed 's/^/  /' || echo '  (no log)'"

echo ""
echo "═══════════════════════════════════════════════════════"
