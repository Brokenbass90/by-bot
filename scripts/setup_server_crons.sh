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
#   1. Dynamic allowlist — weekly coin scanner (Sunday 22:00 UTC)
#   2. DeepSeek weekly cron — analysis + tune + universe (Sunday 22:30 UTC)
#   3. Equity curve autopilot — degradation monitor (Sunday 23:00 UTC)
#   4. Alpaca intraday bridge — 5-min signal check, Mon-Fri market hours
#   5. Alpaca monthly autopilot — 1st of month refresh (already configured)
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
# Remove existing managed entries, then append new ones
CURRENT=$(crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true)

NEW_CRONS=$(cat << CRONEOF
# ── Bybit Bot Autonomous Operations ── $CRON_TAG
#
# 1. Dynamic allowlist — scan best coins per strategy (Sunday 22:00 UTC)
0 22 * * 0 cd $BOT_DIR && $PYTHON scripts/dynamic_allowlist.py --quiet --out-env configs/dynamic_allowlist_latest.env >> logs/dynamic_allowlist.log 2>&1 $CRON_TAG
#
# 2. DeepSeek weekly cron — audit + tune + universe expansion (Sunday 22:30 UTC)
30 22 * * 0 cd $BOT_DIR && $PYTHON scripts/deepseek_weekly_cron.py --quiet >> logs/deepseek_weekly.log 2>&1 $CRON_TAG
#
# 3. Equity curve autopilot — degradation monitor (Sunday 23:00 UTC)
0 23 * * 0 cd $BOT_DIR && $PYTHON scripts/equity_curve_autopilot.py >> logs/equity_autopilot.log 2>&1 $CRON_TAG
#
# 4. Alpaca intraday bridge — every 5 min, Mon-Fri, 14:00-21:00 UTC (US market hours)
# Safe default: dry-run only. Promote to --live only after paper validation.
*/5 14-21 * * 1-5 cd $BOT_DIR && $PYTHON scripts/equities_alpaca_intraday_bridge.py --dry-run --once >> logs/intraday_bridge.log 2>&1 $CRON_TAG
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
echo "[1] Dynamic allowlist (dry-run):"
cd "$BOT_DIR" && $PYTHON scripts/dynamic_allowlist.py --dry-run --quiet 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "[2] Equity autopilot (no-tg):"
cd "$BOT_DIR" && $PYTHON scripts/equity_curve_autopilot.py --no-tg --quiet 2>&1 | tail -3 && ok "OK" || warn "Check logs"

echo ""
echo "[3] Intraday bridge (dry-run):"
cd "$BOT_DIR" && $PYTHON scripts/equities_alpaca_intraday_bridge.py --dry-run --once 2>&1 | tail -5 && ok "OK" || warn "Check logs"

echo ""
echo "================================================"
echo "  Setup complete!"
echo ""
echo "  NEXT STEPS:"
echo "  1. Wait until Sunday 22:00 UTC for first auto-run"
echo "  2. OR test manually:"
echo "     python3 scripts/deepseek_weekly_cron.py"
echo "     python3 scripts/equity_curve_autopilot.py"
echo "  3. Intraday bridge stays in DRY-RUN during Mon-Fri market hours"
echo "     Promote to --live only after paper validation"
echo "  4. Check logs: tail -f logs/dynamic_allowlist.log"
echo "================================================"
