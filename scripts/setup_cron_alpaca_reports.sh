#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOG_DIR="$BOT_DIR/logs"
CRON_DAILY_COMMENT="alpaca_daily_tg_report"
CRON_MONTHLY_COMMENT="alpaca_monthly_tg_report"

mkdir -p "$LOG_DIR"

DAILY_LINE="10 22 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/equities_alpaca_tg_report.py >> $LOG_DIR/alpaca_daily_tg.log 2>&1' # $CRON_DAILY_COMMENT"
MONTHLY_LINE="20 22 1 * * /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/equities_alpaca_tg_report.py --monthly >> $LOG_DIR/alpaca_monthly_tg.log 2>&1' # $CRON_MONTHLY_COMMENT"

tmp="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$CRON_DAILY_COMMENT" | grep -v "$CRON_MONTHLY_COMMENT" > "$tmp" || true
{
  cat "$tmp"
  echo "$DAILY_LINE"
  echo "$MONTHLY_LINE"
} | crontab -
rm -f "$tmp"

echo "Installed cron:"
crontab -l | grep -E "$CRON_DAILY_COMMENT|$CRON_MONTHLY_COMMENT"
