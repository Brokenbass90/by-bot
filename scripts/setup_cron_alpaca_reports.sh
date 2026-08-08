#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOG_DIR="$BOT_DIR/logs"
CRON_MONTHLY_COMMENT="alpaca_monthly_tg_report"

mkdir -p "$LOG_DIR"

MONTHLY_LINE="20 22 1 * * /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && set -a && source configs/alpaca_live_v38.env && source configs/alpaca_live_v38_safe_hold.env && set +a && python3 scripts/equities_alpaca_tg_report.py --monthly >> $LOG_DIR/alpaca_monthly_tg.log 2>&1' # $CRON_MONTHLY_COMMENT"

tmp="$(mktemp)"
crontab -l 2>/dev/null \
  | grep -v "$CRON_MONTHLY_COMMENT" \
  | grep -v "alpaca_daily_tg_report" \
  | grep -v "alpaca_tg_report_watchdog" \
  | grep -v "scripts/equities_alpaca_tg_report.py" \
  | grep -v "scripts/tg_daily_digest.py --alpaca-only" \
  | grep -v "scripts/alpaca_report_freshness_watchdog.py" \
  > "$tmp" || true
{
  cat "$tmp"
  echo "$MONTHLY_LINE"
} | crontab -
rm -f "$tmp"

echo "Installed monthly Alpaca report cron; recurring Alpaca-only Telegram digests removed."
crontab -l | grep -E "$CRON_MONTHLY_COMMENT" || true
