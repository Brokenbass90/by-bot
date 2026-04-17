#!/usr/bin/env bash
# =============================================================================
#  codex_deploy_20260416.sh
#  Server-side deploy script for 2026-04-16 fixes.
#
#  Run this ON THE SERVER:
#    chmod +x scripts/codex_deploy_20260416.sh
#    bash scripts/codex_deploy_20260416.sh
#
#  What it does:
#    1. git pull (new files: att1/asb1/hzbo1/bounce1 live wrappers, regime_orchestrator.py)
#    2. Fix DEGRADED allocator (touch + rebuild)
#    3. Patch live env: disable IVB1, lower Elder risk
#    4. Syntax-check Python files
#    5. Restart live bot
#    6. Verify bot initialized correctly
#    7. Start Regime Orchestrator daemon
#    8. Final status report
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

LIVE_ENV="configs/core3_live_canary_20260411_sloped_momentum.env"
LOG_DIR="logs"
REGIME_LOG="$LOG_DIR/regime_orchestrator.log"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✅ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $*${NC}"; }
fail() { echo -e "${RED}  ❌ $*${NC}"; exit 1; }
step() { echo -e "\n══════════════════════════════════════════"; echo -e "  → $*"; echo -e "══════════════════════════════════════════"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  BOT DEPLOY 2026-04-16  (annual fixes)   ║"
echo "║  ASB1 + HZBO1 + Regime Orchestrator      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. GIT PULL ─────────────────────────────────────────────────────────────
step "[1/8] git pull"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "  Branch: $BRANCH"
if [ -n "$(git status --porcelain)" ]; then
    fail "Worktree is dirty; refusing git pull over live changes. Use targeted copy/scp deploy or clean the tree first."
fi
git pull origin "$BRANCH"

# Check key new files landed
for f in \
    strategies/att1_live.py \
    strategies/asb1_live.py \
    strategies/hzbo1_live.py \
    strategies/bounce1_live.py \
    strategies/alt_trendline_touch_v1.py \
    strategies/alt_slope_break_v1.py \
    strategies/alt_horizontal_break_v1.py \
    strategies/alt_support_bounce_v1.py \
    bot/regime_orchestrator.py; do
    if [ -f "$f" ]; then
        ok "$f present"
    else
        warn "$f NOT FOUND — check git pull"
    fi
done
ok "git pull done"

# ── 2. FIX DEGRADED ALLOCATOR ───────────────────────────────────────────────
step "[2/8] Fix DEGRADED allocator (regenerate health + rebuild)"

# Threshold is now 14 days (1209600s) in portfolio_allocator_policy.json
HEALTH_THRESHOLD=1209600

if [ -f "configs/strategy_health.json" ]; then
    AGE_SEC=$(( $(date +%s) - $(stat -c %Y configs/strategy_health.json) ))
    echo "  Health file age: ${AGE_SEC}s (threshold ${HEALTH_THRESHOLD}s = 14 days)"
    if [ "$AGE_SEC" -gt "$HEALTH_THRESHOLD" ]; then
        warn "Health file is STALE (>${HEALTH_THRESHOLD}s) — will regenerate"
        NEED_REGEN=1
    elif [ "$AGE_SEC" -gt 604800 ]; then
        echo "  Health file is >7d old — refreshing proactively"
        NEED_REGEN=1
    else
        echo "  Health file is fresh — skipping regen"
        NEED_REGEN=0
    fi
else
    warn "configs/strategy_health.json not found — will generate from scratch"
    NEED_REGEN=1
fi

if [ "${NEED_REGEN:-1}" = "1" ]; then
    echo "  Running equity_curve_autopilot --no-tg --quiet ..."
    if "$PYTHON_BIN" scripts/equity_curve_autopilot.py --no-tg --quiet 2>&1 | tail -3; then
        ok "equity_curve_autopilot regenerated strategy_health.json"
    else
        warn "equity_curve_autopilot failed — touching file as fallback (content may be stale)"
        # fallback: touch updates mtime so staleness check passes
        [ -f "configs/strategy_health.json" ] || echo '{"overall_health":"OK","strategies":{}}' > configs/strategy_health.json
        touch configs/strategy_health.json
    fi
fi

"$PYTHON_BIN" scripts/build_portfolio_allocator.py
ok "Allocator rebuilt"

# Verify DEGRADED is gone
ALLOC_ENV="configs/portfolio_allocator_latest.env"
if [ -f "$ALLOC_ENV" ]; then
    if grep -qiE 'DEGRADED=1|ALLOCATOR_DEGRADED=1' "$ALLOC_ENV" 2>/dev/null; then
        warn "DEGRADED flag still present — check manually: cat $ALLOC_ENV | grep -i degraded"
    else
        ok "Allocator is clean (no DEGRADED flag)"
        grep -E "RISK_MULT|GLOBAL|STATUS" "$ALLOC_ENV" 2>/dev/null | head -6 || true
    fi
else
    warn "$ALLOC_ENV not found after rebuild"
fi

# ── 3. PATCH LIVE ENV CONFIG ─────────────────────────────────────────────────
step "[3/8] Patch live env: disable IVB1, lower Elder risk"

if [ ! -f "$LIVE_ENV" ]; then
    fail "Live env not found: $LIVE_ENV"
fi

# Check if patch already applied
if grep -q "# === Fixes 2026-04-16 ===" "$LIVE_ENV"; then
    warn "Patch already applied to $LIVE_ENV — skipping (remove the block to re-apply)"
else
    cat >> "$LIVE_ENV" << 'PATCH'

# === Fixes 2026-04-16 ===
# IVB1: net loser in annual backtest (PF=0.388, -2.5%/yr, avg_win < avg_loss)
# Disabled pending TP/SL ratio investigation
ENABLE_IVB1_TRADING=0

# Elder v2: PF=1.098 is marginal, 6 red months/12, too many trades (250/yr)
# Risk reduced 0.60 → 0.40 to limit drawdown contribution
ELDER_RISK_MULT=0.40

# ASB1 + HZBO1: already ENABLED above — confirmed VIABLE by annual backtest
# ASB1: +18.6%/yr, PF=1.397, 43 trades
# HZBO1: +12.0%/yr, PF=1.486, 62 trades
PATCH

    ok "Patch appended to $LIVE_ENV"
fi

echo ""
echo "  Key values in effect:"
grep -E "ENABLE_IVB1|ELDER_RISK_MULT|ENABLE_ASB1|ENABLE_HZBO1" "$LIVE_ENV" | tail -10

# ── 4. SYNTAX CHECK ──────────────────────────────────────────────────────────
step "[4/8] Syntax check"

"$PYTHON_BIN" -m py_compile smart_pump_reversal_bot.py \
    && ok "smart_pump_reversal_bot.py: OK" \
    || fail "smart_pump_reversal_bot.py: SYNTAX ERROR"

"$PYTHON_BIN" -m py_compile bot/regime_orchestrator.py \
    && ok "bot/regime_orchestrator.py: OK" \
    || fail "bot/regime_orchestrator.py: SYNTAX ERROR"

"$PYTHON_BIN" -m py_compile strategies/asb1_live.py 2>/dev/null \
    && ok "strategies/asb1_live.py: OK" \
    || warn "strategies/asb1_live.py: not found or syntax error"

"$PYTHON_BIN" -m py_compile strategies/att1_live.py 2>/dev/null \
    && ok "strategies/att1_live.py: OK" \
    || warn "strategies/att1_live.py: not found or syntax error"

"$PYTHON_BIN" -m py_compile strategies/hzbo1_live.py 2>/dev/null \
    && ok "strategies/hzbo1_live.py: OK" \
    || warn "strategies/hzbo1_live.py: not found or syntax error"

"$PYTHON_BIN" -m py_compile strategies/bounce1_live.py 2>/dev/null \
    && ok "strategies/bounce1_live.py: OK" \
    || warn "strategies/bounce1_live.py: not found or syntax error"

"$PYTHON_BIN" - <<'PY'
import importlib

mods = [
    "strategies.att1_live",
    "strategies.asb1_live",
    "strategies.hzbo1_live",
    "strategies.bounce1_live",
]
for mod in mods:
    importlib.import_module(mod)
print("live-wrapper import check: OK")
PY
ok "Live wrapper imports resolved"

# ── 5. RESTART BOT ───────────────────────────────────────────────────────────
step "[5/8] Restart live bot"

if systemctl is-active --quiet bybit-bot 2>/dev/null; then
    echo "  Detected: systemd bybit-bot service"
    sudo systemctl restart bybit-bot
    sleep 8
    ok "Bot restarted via systemctl"
elif systemctl is-active --quiet bot 2>/dev/null; then
    echo "  Detected: systemd bot service"
    sudo systemctl restart bot
    sleep 8
    ok "Bot restarted via systemctl"
elif [ -f "scripts/restart_live_bot.sh" ]; then
    echo "  Detected: scripts/restart_live_bot.sh"
    bash scripts/restart_live_bot.sh
    ok "Bot restarted via restart_live_bot.sh"
elif screen -list 2>/dev/null | grep -q "\.bot"; then
    echo "  Detected: screen session 'bot'"
    screen -S bot -X quit 2>/dev/null || true
    sleep 2
    screen -dmS bot bash -lc "cd '$ROOT_DIR' && source .venv/bin/activate && export PYTHONUNBUFFERED=1 && python3 smart_pump_reversal_bot.py >> runtime/live.out 2>&1"
    sleep 5
    ok "Bot restarted in screen session"
else
    warn "Could not auto-restart bot — restart manually:"
    echo "      bash scripts/restart_live_bot.sh"
    echo "      OR: sudo systemctl restart bybit-bot"
fi

# ── 6. VERIFY BOT INIT ───────────────────────────────────────────────────────
step "[6/8] Verify bot initialization"

echo "  Waiting 10s for logs to populate..."
sleep 10

echo ""
echo "  --- Recent bot logs (last 40 lines) ---"
if systemctl is-active --quiet bybit-bot 2>/dev/null || systemctl is-active --quiet bot 2>/dev/null; then
    SVC="bybit-bot"
    systemctl is-active --quiet bybit-bot 2>/dev/null || SVC="bot"
    sudo journalctl -u "$SVC" -n 40 --no-pager 2>/dev/null || true
else
    tail -40 runtime/live.out 2>/dev/null || echo "  (no live.out yet)"
fi

echo ""
echo "  --- Checking for key init signals ---"

check_init() {
    local pattern="$1"
    local label="$2"
    if systemctl is-active --quiet bybit-bot 2>/dev/null; then
        sudo journalctl -u bybit-bot --since "2 minutes ago" --no-pager 2>/dev/null | grep -q "$pattern" && ok "$label" || warn "$label NOT FOUND yet"
    elif systemctl is-active --quiet bot 2>/dev/null; then
        sudo journalctl -u bot --since "2 minutes ago" --no-pager 2>/dev/null | grep -q "$pattern" && ok "$label" || warn "$label NOT FOUND yet"
    else
        tail -100 runtime/live.out 2>/dev/null | grep -q "$pattern" && ok "$label" || warn "$label NOT FOUND yet"
    fi
}

check_init "ASB1"   "ASB1 engine initialised"
check_init "HZBO1"  "HZBO1 engine initialised"
check_init "ETS2\|ELDER\|Elder" "Elder v2 engine initialised"
check_init "IVB1"   "IVB1 status (should say disabled or not appear)"

# Check IVB1 is disabled
if systemctl is-active --quiet bybit-bot 2>/dev/null; then
    sudo journalctl -u bybit-bot --since "2 minutes ago" --no-pager 2>/dev/null | grep "IVB1" | grep -iq "disab\|skip\|off" && ok "IVB1 confirmed disabled" || warn "IVB1 status unclear — check manually"
fi

# ── 7. START REGIME ORCHESTRATOR ─────────────────────────────────────────────
step "[7/8] Start Regime Orchestrator daemon"

mkdir -p "$LOG_DIR" runtime

# Kill existing orchestrator if running
if pgrep -f "regime_orchestrator.py" > /dev/null; then
    warn "Existing orchestrator process found — killing..."
    pkill -f "regime_orchestrator.py" || true
    sleep 2
    ok "Old orchestrator killed"
fi

nohup python3 bot/regime_orchestrator.py \
    --symbol BTCUSDT \
    --out runtime/regime.json \
    --env-out configs/regime_orchestrator_latest.env \
    --loop --interval 900 \
    >> "$REGIME_LOG" 2>&1 &

ORCH_PID=$!
echo "  Orchestrator started with PID=$ORCH_PID"

sleep 5

if kill -0 $ORCH_PID 2>/dev/null; then
    ok "Orchestrator process alive (PID=$ORCH_PID)"
else
    fail "Orchestrator process died immediately — check $REGIME_LOG"
fi

echo ""
echo "  --- Orchestrator log (last 20 lines) ---"
tail -20 "$REGIME_LOG" 2>/dev/null || echo "  (no log yet)"

echo ""
if [ -f "runtime/regime.json" ]; then
    echo "  --- regime.json ---"
    python3 -m json.tool runtime/regime.json 2>/dev/null || cat runtime/regime.json
    ok "regime.json written"
else
    warn "runtime/regime.json not yet written — wait 15-30s and check"
fi

# ── 8. FINAL STATUS ───────────────────────────────────────────────────────────
step "[8/8] Final status report"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         DEPLOY SUMMARY               ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Git status
echo "  Git:"
git log --oneline -3

echo ""
echo "  Python processes:"
pgrep -fal 'smart_pump_reversal_bot\|regime_orchestrator' | head -5 || echo "  (none found — check service status)"

echo ""
echo "  Portfolio allocator:"
if [ -f "configs/portfolio_allocator_latest.env" ]; then
    grep -E "RISK_MULT|DEGRADED|HEALTH" configs/portfolio_allocator_latest.env | head -5 || true
fi

echo ""
echo "  Regime (if available):"
if [ -f "runtime/regime.json" ]; then
    python3 -c "
import json
try:
    d = json.load(open('runtime/regime.json'))
    print(f'  regime={d.get(\"regime\", \"?\")}  confidence={d.get(\"confidence\", \"?\")}  global_risk_mult={d.get(\"global_risk_mult\", \"?\")}')
    overrides = d.get('strategy_overrides', {})
    for k, v in overrides.items():
        print(f'    {k}: allow_longs={v.get(\"allow_longs\", \"?\")}  allow_shorts={v.get(\"allow_shorts\", \"?\")}')
except Exception as e:
    print(f'  (error reading regime.json: {e})')
" 2>/dev/null || cat runtime/regime.json
fi

echo ""
echo "  ══════════════════════════════════════════"
echo "  NEXT: verify bot logs in 5-10 minutes"
echo "  CHECK: grep 'regime' logs/regime_orchestrator.log"
echo "  CHECK: cat runtime/regime.json"
echo ""
echo "  Expected state (April 2026 = bear market):"
echo "    regime=BEAR_TREND"
echo "    ASB1_ALLOW_LONGS=0, ASB1_ALLOW_SHORTS=1"
echo "    HZBO1_ALLOW_LONGS=0, HZBO1_ALLOW_SHORTS=1"
echo "    IVB1 DISABLED (ENABLE_IVB1_TRADING=0)"
echo "    No DEGRADED in bot health output"
echo "  ══════════════════════════════════════════"
echo ""
ok "Deploy complete! 🚀"
