#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# setup_cron_alpaca.sh
# Run this ONCE on the server to set up monthly Alpaca automation.
# The cron job will run on the 1st of each month at 09:30 UTC
# (after US market opens).
#
# Usage: bash scripts/setup_cron_alpaca.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOG_DIR="$BOT_DIR/logs"
CRON_COMMENT="alpaca_monthly_autopilot"

mkdir -p "$LOG_DIR"

# Cron: 30 9 1 * * = 1st of each month at 09:30 UTC
CRON_LINE="30 9 1 * * cd $BOT_DIR && source configs/alpaca_paper_local.env && bash scripts/run_equities_alpaca_monthly_autopilot.sh >> $LOG_DIR/alpaca_monthly.log 2>&1 # $CRON_COMMENT"

# Remove old entry if exists, add new one
(crontab -l 2>/dev/null | grep -v "$CRON_COMMENT" || true; echo "$CRON_LINE") | crontab -

echo "✅ Cron job added:"
crontab -l | grep "$CRON_COMMENT"
echo ""
echo "To run manually NOW (without waiting for cron):"
echo "  cd $BOT_DIR && bash scripts/run_equities_alpaca_monthly_autopilot.sh"
