#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p runtime

if screen -list 2>/dev/null | grep -q "\.bot"; then
  screen -S bot -X quit 2>/dev/null || true
  sleep 2
fi

screen -dmS bot bash -lc "cd '$ROOT_DIR' && source .venv/bin/activate && export PYTHONUNBUFFERED=1 && python3 smart_pump_reversal_bot.py >> runtime/live.out 2>&1"

sleep "${LIVE_RESTART_VERIFY_SEC:-8}"

screen -list | grep "\.bot" >/dev/null
pgrep -fal 'python3 smart_pump_reversal_bot.py' >/dev/null

echo "live bot restarted"
