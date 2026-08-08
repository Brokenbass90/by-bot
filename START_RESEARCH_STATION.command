#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p logs

if pgrep -f "scripts/local_research_station.py --loop" >/dev/null 2>&1; then
  echo "Research station is already running."
else
  screen -dmS research_station_supervisor /bin/bash -lc \
    "cd '$ROOT' && exec '$ROOT/.venv/bin/python' scripts/local_research_station.py --loop --interval-sec 300 >> logs/local_research_station.log 2>&1"
fi

sleep 2
"$ROOT/.venv/bin/python" scripts/local_research_station.py --status-only || true
echo
echo "Status: $ROOT/runtime/local_research_station/status.json"
read -r -p "Нажмите Enter, чтобы закрыть окно..." _
