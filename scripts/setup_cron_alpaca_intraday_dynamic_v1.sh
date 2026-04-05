#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOG_DIR="$BOT_DIR/logs"
CRON_COMMENT="alpaca_intraday_dynamic_v1"

mkdir -p "$LOG_DIR"

CRON_LINE="*/5 14-21 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once >> $LOG_DIR/alpaca_intraday_dynamic_v1.log 2>&1' # $CRON_COMMENT"

(crontab -l 2>/dev/null | grep -v "$CRON_COMMENT" || true; echo "$CRON_LINE") | crontab -

echo "✅ Cron job added:"
crontab -l | grep "$CRON_COMMENT"
echo ""
echo "To run manually NOW:"
echo "  cd $BOT_DIR && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once"
