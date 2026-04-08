#!/usr/bin/env bash
# setup_watchdog_cron.sh
# Install the external watchdog cron on the server.
# Run this ON THE SERVER after setup_systemd_bot.sh.
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOG_DIR="$BOT_DIR/runtime"
CRON_COMMENT="bybit_bot_watchdog"
SCRIPT="$BOT_DIR/scripts/bot_health_watchdog.sh"

mkdir -p "$LOG_DIR"
chmod +x "$SCRIPT"

CRON_LINE="*/2 * * * * /bin/bash -lc 'BOT_DIR=$BOT_DIR $SCRIPT >> $LOG_DIR/watchdog.log 2>&1' # $CRON_COMMENT"

# Remove old entry and add new
(crontab -l 2>/dev/null | grep -v "$CRON_COMMENT" || true; echo "$CRON_LINE") | crontab -

echo "✅ Watchdog cron installed (runs every 2 minutes):"
crontab -l | grep "$CRON_COMMENT"
echo ""
echo "To enable auto-restart (use with caution — requires systemd):"
echo "  Add WATCHDOG_AUTO_RESTART=1 to your .env or export it before the cron line"
echo ""
echo "To test immediately:"
echo "  BOT_DIR=$BOT_DIR bash $SCRIPT"
