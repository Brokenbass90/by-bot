#!/usr/bin/env bash
# Mid-month position health check
# Cron: 0 15 * * 3 cd /root/by-bot && bash scripts/run_equities_midmonth_check.sh >> logs/alpaca_midmonth.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL_ENV="${ALPACA_AUTOPILOT_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
if [[ -f "$LOCAL_ENV" ]]; then
  set -a
  source "$LOCAL_ENV"
  set +a
fi

echo "midmonth check: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# Install yfinance if needed
pip install yfinance --break-system-packages -q 2>/dev/null || true

python3 scripts/equities_midmonth_monitor.py
