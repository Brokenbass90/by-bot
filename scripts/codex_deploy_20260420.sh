#!/usr/bin/env bash
# =============================================================================
#  codex_deploy_20260420.sh — Deploy script for 2026-04-20 session
#
#  Run this ON THE SERVER after Codex pushes the branch:
#    chmod +x scripts/codex_deploy_20260420.sh
#    bash scripts/codex_deploy_20260420.sh
#
#  What this batch includes:
#    1.  SOB1 — session_open_breakout_v1 wired into live bot (DISABLED by default)
#    2.  BE protection — breakdown / IVB1 / Elder move SL to BE after TP1
#    3.  Dead zone filter — NO_ENTRY_HOURS_UTC=0,1,2 (00:00-02:00 UTC blocked)
#    4.  Direction correlation cap — MAX_SAME_DIRECTION_POSITIONS env var
#    5.  strategy_pause.env loaded at bot startup (Phase 3 loop closure)
#    6.  BTC dominance overlay wired into build_regime_state.py
#    7.  live_vs_backtest_monitor.py — rolling 30d degradation detector
#    8.  auto_apply_research_winner.py + promote_wf22_winner.py
#    9.  setup_server_crons.sh updated with all new crons (#17/#18)
#   10.  Web analytics endpoint + UI panel (/api/strategy-stats)
#   11.  SOB1 added to strategy_profile_registry.json (sob1_all_regimes)
#
#  After deploy:
#    → Set ENABLE_SOB1_TRADING=1 ONLY after WF-22 validation passes
#    → Wednesday 2026-04-23 12:00: check WF-22 results and promote winners
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✅ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $*${NC}"; }
fail() { echo -e "${RED}  ❌ $*${NC}"; exit 1; }
step() { echo -e "\n══════════════════════════════════════════"; echo "  → $*"; echo -e "══════════════════════════════════════════"; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  BOT DEPLOY 2026-04-20 (profitability + Phase 3)    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. GIT PULL ──────────────────────────────────────────────────────────────
step "[1/7] git pull"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "  Branch: $BRANCH"
if [ -n "$(git status --porcelain)" ]; then
    fail "Worktree dirty. Stash or commit local changes first."
fi
git pull origin "$BRANCH"
ok "Pulled branch: $BRANCH"

# ── 2. VERIFY KEY FILES ───────────────────────────────────────────────────────
step "[2/7] Verify key new/modified files"
for f in \
    strategies/session_open_breakout_v1.py \
    strategies/alt_inplay_breakdown_v1.py \
    strategies/impulse_volume_breakout_v1.py \
    strategies/elder_triple_screen_v2.py \
    scripts/live_vs_backtest_monitor.py \
    scripts/promote_wf22_winner.py \
    scripts/build_btc_dominance_state.py \
    scripts/auto_apply_research_winner.py \
    configs/strategy_profile_registry.json \
    configs/portfolio_allocator_policy.json \
; do
    [ -f "$f" ] && ok "$f" || fail "MISSING: $f"
done

# ── 3. SYNTAX CHECK ──────────────────────────────────────────────────────────
step "[3/7] Python syntax check"
for f in \
    smart_pump_reversal_bot.py \
    strategies/session_open_breakout_v1.py \
    strategies/alt_inplay_breakdown_v1.py \
    strategies/impulse_volume_breakout_v1.py \
    strategies/elder_triple_screen_v2.py \
    scripts/live_vs_backtest_monitor.py \
    scripts/promote_wf22_winner.py \
    scripts/build_btc_dominance_state.py \
; do
    $PYTHON_BIN -m py_compile "$f" && ok "$f" || fail "Syntax error: $f"
done

# ── 4. ALLOCATOR / ROUTER REBUILD ─────────────────────────────────────────────
step "[4/7] Rebuild allocator + symbol router"
$PYTHON_BIN scripts/build_regime_state.py          && ok "regime state OK"
$PYTHON_BIN scripts/build_symbol_router.py --quiet && ok "symbol router OK"
$PYTHON_BIN scripts/build_portfolio_allocator.py   && ok "portfolio allocator OK"

# ── 5. UPDATE CRONS ───────────────────────────────────────────────────────────
step "[5/7] Install cron entries"
bash scripts/setup_server_crons.sh 2>&1 | tail -5
ok "Crons installed"

# ── 6. RESTART BOT ───────────────────────────────────────────────────────────
step "[6/7] Restart live bot"
BOT_PID_FILE="runtime/bot.pid"
if [ -f "$BOT_PID_FILE" ]; then
    OLD_PID=$(cat "$BOT_PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        warn "Stopping bot PID $OLD_PID..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 3
    fi
fi

LIVE_ENV=$(ls configs/*.env 2>/dev/null | grep -v "local\|paper\|test\|sample" | head -1)
if [ -z "$LIVE_ENV" ]; then
    warn "No live .env found — bot NOT restarted. Start manually."
else
    echo "  Using env: $LIVE_ENV"
    nohup $PYTHON_BIN smart_pump_reversal_bot.py --config "$LIVE_ENV" \
        >> logs/bot.log 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$BOT_PID_FILE"
    sleep 4
    if kill -0 "$NEW_PID" 2>/dev/null; then
        ok "Bot started (PID $NEW_PID)"
    else
        fail "Bot failed to start — check logs/bot.log"
    fi
fi

# ── 7. FINAL STATUS ──────────────────────────────────────────────────────────
step "[7/7] Status"
echo ""
echo "  ✅ Deploy complete!"
echo ""
echo "  KEY ACTIONS NEEDED:"
echo "  1. Queue SOB1 WF-22: python3 scripts/run_strategy_autoresearch.py \\"
echo "       --strategy session_open_breakout_v1 --mode wf22 --symbols BTCUSDT,ETHUSDT,SOLUSDT"
echo ""
echo "  2. Wednesday 2026-04-23 12:00 UTC — check WF-22 results:"
echo "       python3 scripts/promote_wf22_winner.py --strategy breakdown_v1 --wf-result runtime/wf22/breakdown_v1_latest.json"
echo "       python3 scripts/promote_wf22_winner.py --strategy session_open_breakout_v1 --wf-result runtime/wf22/sob1_latest.json"
echo ""
echo "  3. Enable SOB1 ONLY after WF-22 passes:"
echo "       echo 'ENABLE_SOB1_TRADING=1' >> configs/your_live.env && kill -HUP \$(cat runtime/bot.pid)"
echo ""
echo "  4. Check logs:"
echo "       tail -f logs/bot.log"
echo "       tail -f logs/live_vs_backtest_monitor.log"
echo "       tail -f logs/btc_dominance.log"
echo ""
echo "  NO_ENTRY_HOURS_UTC=0,1,2  (default, 3h dead zone active)"
echo "  MAX_SAME_DIRECTION_POSITIONS=0  (default off — set to 2 to activate)"
echo ""
ok "Done. Good luck 🚀"
