#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOG_DIR="$BOT_DIR/logs"
CRON_DAILY_COMMENT="alpaca_daily_tg_report"
CRON_MONTHLY_COMMENT="alpaca_monthly_tg_report"
CRON_WATCHDOG_COMMENT="alpaca_tg_report_watchdog"

mkdir -p "$LOG_DIR"

DAILY_LINE="10 22 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/tg_daily_digest.py --alpaca-only --status-key alpaca_postclose >> $LOG_DIR/alpaca_postclose_report.log 2>&1' # $CRON_DAILY_COMMENT"
MONTHLY_LINE="20 22 1 * * /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && set -a && source configs/alpaca_live_v38.env && source configs/alpaca_live_v38_safe_hold.env && set +a && python3 scripts/equities_alpaca_tg_report.py --monthly >> $LOG_DIR/alpaca_monthly_tg.log 2>&1' # $CRON_MONTHLY_COMMENT"
WATCHDOG_LINE="0 23 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/alpaca_report_freshness_watchdog.py >> $LOG_DIR/alpaca_report_watchdog.log 2>&1' # $CRON_WATCHDOG_COMMENT"

tmp="$(mktemp)"
crontab -l 2>/dev/null \
  | grep -v "$CRON_DAILY_COMMENT" \
  | grep -v "$CRON_MONTHLY_COMMENT" \
  | grep -v "$CRON_WATCHDOG_COMMENT" \
  | grep -v "scripts/equities_alpaca_tg_report.py" \
  | grep -v "scripts/tg_daily_digest.py --alpaca-only" \
  | grep -v "scripts/alpaca_report_freshness_watchdog.py" \
  > "$tmp" || true
{
  cat "$tmp"
  echo "$DAILY_LINE"
  echo "$MONTHLY_LINE"
  echo "$WATCHDOG_LINE"
} | crontab -
rm -f "$tmp"

echo "Installed cron:"
crontab -l | grep -E "$CRON_DAILY_COMMENT|$CRON_MONTHLY_COMMENT|$CRON_WATCHDOG_COMMENT"
