#!/bin/bash
# =============================================================================
# Server Cron Setup — Bybit Bot Autonomous Operations
# =============================================================================
# Run this ONCE on the server to activate all scheduled tasks.
#
# Usage:
#   bash scripts/setup_server_crons.sh
#
# What it sets up:
#   1. Regime orchestrator — hourly BTC regime classifier
#   2. Symbol router — 6h per-strategy basket rebuild
#   3. Portfolio allocator — hourly risk / sleeve overlay rebuild
#   4. Control-plane watchdog — freshness check + self-heal
#   5. Geometry state builder — deterministic chart context from cached OHLCV
#   6. Operator snapshot builder — compact truth pack for AI/operator context
#   7. Strategy health timeline — weekly historical health context for replay/operator
#   8. DeepSeek weekly cron — analysis + tune + universe (Sunday 22:30 UTC)
#   9. Equity curve autopilot — degradation monitor (Sunday 23:00 UTC)
#  10. Alpaca intraday dynamic bridge — 5-min signal check, Mon-Fri market hours
#
# After running: verify with `crontab -l`
# Logs: /root/by-bot/logs/  (auto-created)
#
# To remove all managed crons: bash scripts/setup_server_crons.sh --remove
# =============================================================================

set -e

BOT_DIR="/root/by-bot"
PYTHON="$BOT_DIR/.venv/bin/python"
CRON_TAG="# bybit-bot-managed"

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}✗  $1${NC}"; }

echo "================================================"
echo "  Bybit Bot — Server Cron Setup"
echo "  Dir: $BOT_DIR"
echo "================================================"

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [ ! -d "$BOT_DIR" ]; then
    err "Bot directory not found: $BOT_DIR"
    exit 1
fi
if [ ! -x "$PYTHON" ]; then
    err "Python venv not found: $PYTHON"
    exit 1
fi
for req in \
    "$BOT_DIR/scripts/build_regime_state.py" \
    "$BOT_DIR/scripts/build_symbol_router.py" \
    "$BOT_DIR/scripts/build_portfolio_allocator.py" \
    "$BOT_DIR/scripts/control_plane_watchdog.py" \
    "$BOT_DIR/scripts/build_geometry_state.py" \
    "$BOT_DIR/scripts/build_operator_snapshot.py" \
    "$BOT_DIR/scripts/build_strategy_health_timeline.py" \
    "$BOT_DIR/scripts/dynamic_allowlist.py" \
    "$BOT_DIR/bot/strategy_health_timeline.py" \
    "$BOT_DIR/scripts/run_equities_alpaca_intraday_dynamic_v1.sh" \
    "$BOT_DIR/configs/strategy_profile_registry.json" \
    "$BOT_DIR/configs/portfolio_allocator_policy.json" \
    "$BOT_DIR/configs/strategy_health.json"
do
    if [ ! -f "$req" ]; then
        err "Required file not found: $req"
        exit 1
    fi
done

if [ ! -f "$BOT_DIR/scripts/dynamic_allowlist.py" ]; then
    err "dynamic_allowlist.py not found — pull latest code first"
    exit 1
fi

# ── Remove mode ────────────────────────────────────────────────────────────────
if [ "$1" = "--remove" ]; then
    warn "Removing all managed cron entries..."
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab -
    ok "All managed crons removed"
    crontab -l 2>/dev/null | head -20 || echo "(crontab empty)"
    exit 0
fi

# ── Create logs directory ──────────────────────────────────────────────────────
mkdir -p "$BOT_DIR/logs"
ok "Logs dir: $BOT_DIR/logs"

# ── Build new cron entries ─────────────────────────────────────────────────────
# Remove existing managed entries plus known legacy autonomous duplicates.
CURRENT=$(
    crontab -l 2>/dev/null \
        | grep -v "$CRON_TAG" \
        | grep -v "scripts/deepseek_weekly_cron.py >> logs/deepseek_weekly.log" \
        | grep -v "scripts/equity_curve_autopilot.py >> logs/equity_curve.log" \
        | grep -v "scripts/control_plane_watchdog.py --repair --quiet >> logs/control_plane_watchdog.log" \
        | grep -v "scripts/build_geometry_state.py --quiet >> logs/geometry_state.log" \
        | grep -v "scripts/build_operator_snapshot.py --quiet >> logs/operator_snapshot.log" \
        | grep -v "scripts/build_strategy_health_timeline.py --quiet >> logs/strategy_health_timeline.log" \
        | grep -v "scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once >> /root/by-bot/logs/alpaca_intraday_dynamic_v1.log" \
        | grep -v "scripts/bot_health_watchdog.sh" \
        | grep -v "^# 1\\. Dynamic allowlist" \
        | grep -v "^# 2\\. DeepSeek weekly cron" \
        | grep -v "^# 3\\. Equity curve autopilot" \
        | grep -v "^# 4\\. Alpaca intraday bridge" \
        | grep -v "^# Safe default: dry-run only\\. Promote to --live only after paper validation\\." \
        || true
)

NEW_CRONS=$(cat << CRONEOF
# ── Bybit Bot Autonomous Operations ── $CRON_TAG
#
# 0. Bot health watchdog — every 2 min: heartbeat check + auto-restart + router recovery
*/2 * * * * WATCHDOG_AUTO_RESTART=1 BOT_DIR=$BOT_DIR /bin/bash -lc 'cd $BOT_DIR && bash scripts/bot_health_watchdog.sh >> runtime/watchdog.log 2>&1' $CRON_TAG
#
# 1. Regime orchestrator — hourly regime snapshot / live overlay
0 * * * * cd $BOT_DIR && $PYTHON scripts/build_regime_state.py >> logs/regime_orchestrator.log 2>&1 $CRON_TAG
#
# 2. Symbol router — rebuild per-strategy symbol baskets every 4 hours (with 3-retry auto-recovery)
3 */4 * * * cd $BOT_DIR && $PYTHON scripts/build_symbol_router.py --quiet --scan-retries 3 --scan-retry-delay-sec 30 >> logs/symbol_router.log 2>&1 $CRON_TAG
#
# 3. Portfolio allocator — hourly sleeve/risk overlay from regime + router + health
5 * * * * cd $BOT_DIR && $PYTHON scripts/build_portfolio_allocator.py >> logs/portfolio_allocator.log 2>&1 $CRON_TAG
#
# 4. Control-plane watchdog — detect degraded/stale state and self-heal every 15 min
*/15 * * * * cd $BOT_DIR && $PYTHON scripts/control_plane_watchdog.py --repair --quiet >> logs/control_plane_watchdog.log 2>&1 $CRON_TAG
#
# 5. Geometry state builder — deterministic levels / channels / compression for active symbols
12 * * * * cd $BOT_DIR && $PYTHON scripts/build_geometry_state.py --quiet >> logs/geometry_state.log 2>&1 $CRON_TAG
#
# 6. Operator snapshot builder — compact truth pack for AI/operator context
14 * * * * cd $BOT_DIR && $PYTHON scripts/build_operator_snapshot.py --quiet >> logs/operator_snapshot.log 2>&1 $CRON_TAG
#
# 7. Slow bounded research queue — one low-priority research process at a time
17 * * * * cd $BOT_DIR && $PYTHON scripts/run_nightly_research_queue.py --quiet >> logs/research_nightly.log 2>&1 $CRON_TAG
#
# 8. Strategy health timeline — historical health context for replay/operator
5 23 * * 0 cd $BOT_DIR && $PYTHON scripts/build_strategy_health_timeline.py --quiet >> logs/strategy_health_timeline.log 2>&1 $CRON_TAG
#
# 9. DeepSeek weekly cron — audit + tune + universe expansion (Sunday 22:30 UTC)
30 22 * * 0 cd $BOT_DIR && $PYTHON scripts/deepseek_weekly_cron.py --quiet >> logs/deepseek_weekly.log 2>&1 $CRON_TAG
#
# 10. Equity curve autopilot — degradation monitor (Sunday 23:00 UTC)
0 23 * * 0 cd $BOT_DIR && $PYTHON scripts/equity_curve_autopilot.py >> logs/equity_autopilot.log 2>&1 $CRON_TAG
#
# 11. Alpaca intraday bridge — every 5 min, Mon-Fri, 14:00-21:00 UTC (US market hours)
*/5 14-21 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once >> logs/alpaca_intraday_dynamic_v1.log 2>&1' $CRON_TAG
#
CRONEOF
)

# Write combined crontab
(echo "$CURRENT"; echo "$NEW_CRONS") | crontab -

echo ""
ok "Cron entries installed. Current crontab:"
echo "--------------------------------------------"
crontab -l
echo "--------------------------------------------"

# ── Immediate dry-run tests ────────────────────────────────────────────────────
echo ""
echo "Running quick sanity checks..."

echo ""
echo "[1] Regime orchestrator (dry-run):"
cd "$BOT_DIR" && $PYTHON scripts/build_regime_state.py --dry-run 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[2] Symbol router (dry-run):"
cd "$BOT_DIR" && $PYTHON scripts/build_symbol_router.py --dry-run --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[3] Portfolio allocator (dry-run):"
cd "$BOT_DIR" && $PYTHON scripts/build_portfolio_allocator.py --dry-run 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[4] Equity autopilot (no-tg):"
cd "$BOT_DIR" && $PYTHON scripts/equity_curve_autopilot.py --no-tg --quiet 2>&1 | tail -3 && ok "OK" || warn "Check logs"

echo ""
echo "[5] Control-plane watchdog (dry-run):"
cd "$BOT_DIR" && $PYTHON scripts/control_plane_watchdog.py 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[6] Geometry state builder:"
cd "$BOT_DIR" && $PYTHON scripts/build_geometry_state.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[7] Strategy health timeline builder:"
cd "$BOT_DIR" && $PYTHON scripts/build_strategy_health_timeline.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[8] Operator snapshot builder:"
cd "$BOT_DIR" && $PYTHON scripts/build_operator_snapshot.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[9] Intraday bridge (live paper once):"
cd "$BOT_DIR" && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "================================================"
echo "  Setup complete!"
echo ""
echo "  NEXT STEPS:"
echo "  1. Regime/allocator now rebuild hourly; router rebuilds daily at 00:03 UTC"
echo "  1. Regime/allocator now rebuild hourly; router rebuilds every 6h; watchdog checks every 15m"
echo "  2. OR test manually:"
echo "     python3 scripts/build_regime_state.py"
echo "     python3 scripts/build_symbol_router.py --quiet"
echo "     python3 scripts/build_portfolio_allocator.py"
echo "     python3 scripts/deepseek_weekly_cron.py"
echo "     python3 scripts/equity_curve_autopilot.py"
echo "  3. Check logs: tail -f logs/regime_orchestrator.log"
echo "     tail -f logs/symbol_router.log"
echo "     tail -f logs/portfolio_allocator.log"
echo "================================================"
