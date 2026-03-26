#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p logs

CRON_LINE="17 * * * * /bin/bash -lc 'cd $PWD && bash scripts/run_live_health_guard.sh >> $PWD/logs/live_health_guard.log 2>&1'"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

crontab -l 2>/dev/null | grep -v 'run_live_health_guard.sh' > "$tmp" || true
printf "%s\n" "$CRON_LINE" >> "$tmp"
crontab "$tmp"

echo "Installed cron:"
echo "$CRON_LINE"
