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
#   7. Research process guard — kills stale autoresearch/backtest rows
#   8. Self-audit report — slow evidence-driven diagnosis of current blockers
#   9. Project doctor report — structural project diagnosis for AI/operator
#  10. Strategy health timeline — weekly historical health context for replay/operator
#  11. DeepSeek weekly cron — analysis + tune + universe (Sunday 22:30 UTC)
#  12. Equity curve autopilot — degradation monitor (Sunday 23:00 UTC)
#  13. Alpaca intraday dynamic bridge — 5-min signal check, Mon-Fri market hours
#  14. Auto-apply research winners — daily 06:00 UTC
#  15. Funding-rate snapshot refresh — every 5 min
#  16. Daily Telegram health digest — 08:00 UTC every day
#  17. Alpaca monthly autopilot — 1st of month 09:30 UTC
#  18. BTC dominance overlay — every 4h (alt_bias / alt_risk_mult)
#  19. Live vs backtest monitor — every 4h (Phase 3 degradation detector)
#  20. Live vs backtest monitor — daily 07:00 UTC (with TG alert on degrade)
#  21. Weekly live-vs-backtest report — Friday 07:30 UTC
#  22. Weekly trade-forensics AI report — Friday 07:45 UTC
#  23. AI full-context pack — every 5 min
#  24. Crypto setup blocker report — every 10 min
#  25. Freshness watchdog — control-plane stale-state alert
#  26. Stop-integrity watchdog — P0 TP/SL compression alert
#  27. Alpaca post-close truth report — 22:10 UTC weekdays
#  28. Alpaca report delivery watchdog — 23:00 UTC weekdays
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
    "$BOT_DIR/scripts/build_ai_full_context.py" \
    "$BOT_DIR/scripts/build_ai_extras.py" \
    "$BOT_DIR/scripts/build_ai_ohlc_and_logs.py" \
    "$BOT_DIR/scripts/build_crypto_setup_blocker_report.py" \
    "$BOT_DIR/scripts/build_self_audit_report.py" \
    "$BOT_DIR/scripts/build_project_doctor_report.py" \
    "$BOT_DIR/scripts/build_strategy_health_timeline.py" \
    "$BOT_DIR/scripts/research_process_guard.py" \
    "$BOT_DIR/scripts/dynamic_allowlist.py" \
    "$BOT_DIR/bot/strategy_health_timeline.py" \
    "$BOT_DIR/scripts/run_equities_alpaca_intraday_dynamic_v1.sh" \
    "$BOT_DIR/configs/strategy_profile_registry.json" \
    "$BOT_DIR/configs/portfolio_allocator_policy.json" \
    "$BOT_DIR/configs/strategy_health.json" \
    "$BOT_DIR/scripts/build_btc_dominance_state.py" \
    "$BOT_DIR/scripts/live_vs_backtest_monitor.py" \
    "$BOT_DIR/scripts/weekly_live_vs_backtest_report.py" \
    "$BOT_DIR/scripts/weekly_trade_forensics_ai_report.py" \
    "$BOT_DIR/scripts/promote_wf22_winner.py" \
    "$BOT_DIR/scripts/funding_rate_fetcher.py" \
    "$BOT_DIR/scripts/freshness_watchdog.py" \
    "$BOT_DIR/scripts/stop_integrity_watchdog.py" \
    "$BOT_DIR/scripts/alpaca_report_freshness_watchdog.py"
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
        | grep -v "scripts/build_ai_full_context.py --quiet >> logs/ai_full_context.log" \
        | grep -v "scripts/build_ai_extras.py --quiet >> logs/ai_extras.log" \
        | grep -v "scripts/build_ai_ohlc_and_logs.py --quiet >> logs/ai_ohlc_and_logs.log" \
        | grep -v "scripts/build_crypto_setup_blocker_report.py --quiet >> logs/crypto_blocker.log" \
        | grep -v "scripts/freshness_watchdog.py" \
        | grep -v "scripts/stop_integrity_watchdog.py" \
        | grep -v "scripts/tg_daily_digest.py --alpaca-only" \
        | grep -v "scripts/alpaca_report_freshness_watchdog.py" \
        | grep -v "scripts/equities_alpaca_tg_report.py" \
        | grep -v "scripts/build_self_audit_report.py --quiet >> logs/self_audit.log" \
        | grep -v "scripts/build_project_doctor_report.py --quiet >> logs/project_doctor.log" \
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
# 0. Bot health watchdog — every 2 min: heartbeat check + guarded auto-restart + router recovery
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
# 4b. Freshness watchdog — make stale router/regime/allocator inputs loud every 30 min
*/30 * * * * cd $BOT_DIR && $PYTHON scripts/freshness_watchdog.py --json runtime/freshness_report.json --telegram >> logs/freshness_watchdog.log 2>&1 $CRON_TAG
#
# 4c. Stop-integrity watchdog — catch P0 TP/SL compression or missing request telemetry every 10 min
*/10 * * * * cd $BOT_DIR && $PYTHON scripts/stop_integrity_watchdog.py --lookback-hours 24 --json runtime/stop_integrity_report.json --telegram >> logs/stop_integrity_watchdog.log 2>&1 $CRON_TAG
#
# 5. Geometry state builder — deterministic levels / channels / compression for active symbols
12 * * * * cd $BOT_DIR && $PYTHON scripts/build_geometry_state.py --quiet >> logs/geometry_state.log 2>&1 $CRON_TAG
#
# 6. Operator snapshot builder — compact truth pack for AI/operator context
14 * * * * cd $BOT_DIR && $PYTHON scripts/build_operator_snapshot.py --quiet >> logs/operator_snapshot.log 2>&1 $CRON_TAG
#
# 6b. AI full-context pack — every 5 min: scanner cards + no-signal + trades + research status
*/5 * * * * cd $BOT_DIR && $PYTHON scripts/build_ai_full_context.py --quiet >> logs/ai_full_context.log 2>&1 $CRON_TAG
#
# 6c. AI extras pack — every 5 min: deeper trades + errors + indicators + memory
*/5 * * * * cd $BOT_DIR && $PYTHON scripts/build_ai_extras.py --quiet >> logs/ai_extras.log 2>&1 $CRON_TAG
#
# 6d. AI OHLC/logs pack — every 5 min: top setup candles + compact live log tail
*/5 * * * * cd $BOT_DIR && $PYTHON scripts/build_ai_ohlc_and_logs.py --quiet >> logs/ai_ohlc_and_logs.log 2>&1 $CRON_TAG
#
# 6e. Crypto setup blocker report — every 10 min: scanner -> live sleeve blocker diagnosis
*/10 * * * * cd $BOT_DIR && $PYTHON scripts/build_crypto_setup_blocker_report.py --quiet >> logs/crypto_blocker.log 2>&1 $CRON_TAG
#
# 7. Slow bounded research queue — one low-priority research process at a time
17 * * * * cd $BOT_DIR && $PYTHON scripts/run_nightly_research_queue.py --quiet >> logs/research_nightly.log 2>&1 $CRON_TAG
#
# 8. Research process guard — keep unattended sweeps from blocking the queue for days
*/10 * * * * cd $BOT_DIR && $PYTHON scripts/research_process_guard.py --repair --quiet >> logs/research_process_guard.log 2>&1 $CRON_TAG
#
# 9. Self-audit report — slow diagnosis of live blockers every 2 hours
20 */2 * * * cd $BOT_DIR && $PYTHON scripts/build_self_audit_report.py --quiet >> logs/self_audit.log 2>&1 $CRON_TAG
#
# 10. Project doctor — structural diagnosis for AI/operator context
22 */2 * * * cd $BOT_DIR && $PYTHON scripts/build_project_doctor_report.py --quiet >> logs/project_doctor.log 2>&1 $CRON_TAG
#
# 11. Strategy health timeline — historical health context for replay/operator
5 23 * * 0 cd $BOT_DIR && $PYTHON scripts/build_strategy_health_timeline.py --quiet >> logs/strategy_health_timeline.log 2>&1 $CRON_TAG
#
# 12. DeepSeek weekly cron — audit + tune + universe expansion (Sunday 22:30 UTC)
30 22 * * 0 cd $BOT_DIR && $PYTHON scripts/deepseek_weekly_cron.py --quiet >> logs/deepseek_weekly.log 2>&1 $CRON_TAG
#
# 13. Equity curve autopilot — degradation monitor (Wednesday 03:00 + Sunday 23:00 UTC)
# Runs TWICE weekly so health file never goes stale (threshold = 14 days, but 3.5d is safe margin)
0 3 * * 3 cd $BOT_DIR && $PYTHON scripts/equity_curve_autopilot.py --no-tg --quiet >> logs/equity_autopilot.log 2>&1 $CRON_TAG
0 23 * * 0 cd $BOT_DIR && $PYTHON scripts/equity_curve_autopilot.py >> logs/equity_autopilot.log 2>&1 $CRON_TAG
#
# 14. Alpaca intraday bridge — every 5 min, Mon-Fri, 14:00-21:00 UTC (US market hours)
*/5 14-21 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once >> logs/alpaca_intraday_dynamic_v1.log 2>&1' $CRON_TAG
#
# 15. Funding-rate snapshot refresh — every 5 min for funding_rev sleeve
*/5 * * * * cd $BOT_DIR && $PYTHON scripts/funding_rate_fetcher.py --once --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT >> logs/funding_rate_fetcher.log 2>&1 $CRON_TAG
#
# 16. Auto-apply research winners — daily at 06:00 UTC, after nightly research completes
0 6 * * * cd $BOT_DIR && $PYTHON scripts/auto_apply_research_winner.py >> logs/auto_apply.log 2>&1 $CRON_TAG
#
# 17. Daily Telegram health digest — every morning at 08:00 UTC
# Reports: CB state, regime, allocator, open trades, Alpaca P&L + picks
0 8 * * * /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/tg_daily_digest.py >> logs/tg_daily_digest.log 2>&1' $CRON_TAG
#
# 17b. Alpaca post-close truth report — recurring weekdays after the US close
10 22 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/tg_daily_digest.py --alpaca-only --status-key alpaca_postclose >> logs/alpaca_postclose_report.log 2>&1' $CRON_TAG
#
# 17c. Alpaca report delivery watchdog — alert if today's post-close delivery is absent
0 23 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/alpaca_report_freshness_watchdog.py >> logs/alpaca_report_watchdog.log 2>&1' $CRON_TAG
#
# 18. Alpaca monthly autopilot — 1st of each month at 09:30 UTC (after market open)
30 9 1 * * /bin/bash -lc 'cd $BOT_DIR && bash scripts/run_equities_alpaca_monthly_autopilot.sh >> logs/alpaca_monthly.log 2>&1' $CRON_TAG
#
# 19. BTC dominance overlay — every 4h (Phase 3: alt_bias / ALT_RISK_MULT for regime env)
# Writes runtime/btc_dominance_state.json, read by build_regime_state.py next cycle
10 */4 * * * cd $BOT_DIR && $PYTHON scripts/build_btc_dominance_state.py >> logs/btc_dominance.log 2>&1 $CRON_TAG
#
# 20. Live vs backtest monitor — every 4h (Phase 3: degrade detection, writes strategy_pause.env)
# Bot loads strategy_pause.env on startup via load_dotenv(override=True)
25 */4 * * * cd $BOT_DIR && $PYTHON scripts/live_vs_backtest_monitor.py >> logs/strategy_monitor.log 2>&1 $CRON_TAG
#
# 21. Weekly live-vs-backtest comparison report — Friday 07:30 UTC
30 7 * * 5 cd $BOT_DIR && $PYTHON scripts/weekly_live_vs_backtest_report.py --telegram >> logs/weekly_live_vs_backtest.log 2>&1 $CRON_TAG
#
# 22. Weekly trade-forensics AI report — Friday 07:45 UTC
# Reads live/backtest trades, classifies stop/entry/exit quality, and asks DeepSeek for a short interpretation when enabled.
45 7 * * 5 cd $BOT_DIR && $PYTHON scripts/weekly_trade_forensics_ai_report.py --telegram --ai >> logs/weekly_trade_forensics_ai.log 2>&1 $CRON_TAG
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
echo "[6] Freshness watchdog:"
cd "$BOT_DIR" && $PYTHON scripts/freshness_watchdog.py --json runtime/freshness_report.json 2>&1 | tail -8 && ok "OK" || warn "Check logs"

echo ""
echo "[7] Stop-integrity watchdog:"
cd "$BOT_DIR" && $PYTHON scripts/stop_integrity_watchdog.py --lookback-hours 24 --json runtime/stop_integrity_report.json 2>&1 | tail -8 && ok "OK" || warn "Check logs"

echo ""
echo "[8] Geometry state builder:"
cd "$BOT_DIR" && $PYTHON scripts/build_geometry_state.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[9] Self-audit report:"
cd "$BOT_DIR" && $PYTHON scripts/build_self_audit_report.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[10] AI full-context pack:"
cd "$BOT_DIR" && $PYTHON scripts/build_ai_full_context.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[11] Crypto setup blocker report:"
cd "$BOT_DIR" && $PYTHON scripts/build_crypto_setup_blocker_report.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[12] Project doctor report:"
cd "$BOT_DIR" && $PYTHON scripts/build_project_doctor_report.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[13] Strategy health timeline builder:"
cd "$BOT_DIR" && $PYTHON scripts/build_strategy_health_timeline.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[14] Operator snapshot builder:"
cd "$BOT_DIR" && $PYTHON scripts/build_operator_snapshot.py --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[15] Intraday bridge (live paper once):"
cd "$BOT_DIR" && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "================================================"
echo "  Setup complete!"
echo ""
echo "  NEXT STEPS:"
echo "  1. Regime/allocator now rebuild hourly; router rebuilds every 4h"
echo "  2. Control-plane/watchdog checks run every 10-30m"
echo "  3. OR test manually:"
echo "     python3 scripts/build_regime_state.py"
echo "     python3 scripts/build_symbol_router.py --quiet"
echo "     python3 scripts/build_portfolio_allocator.py"
echo "     python3 scripts/deepseek_weekly_cron.py"
echo "     python3 scripts/equity_curve_autopilot.py"
echo "  4. Check logs: tail -f logs/regime_orchestrator.log"
echo "     tail -f logs/symbol_router.log"
echo "     tail -f logs/portfolio_allocator.log"
echo "================================================"
