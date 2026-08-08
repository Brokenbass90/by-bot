#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.tradingstation.research-station"

echo "Research Station / launchd"
if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
  echo "  supervisor: RUNNING"
else
  echo "  supervisor: NOT RUNNING"
  echo "  repair: double-click START_RESEARCH_STATION.command"
fi

echo
"${ROOT}/.venv/bin/python" "${ROOT}/scripts/local_research_station.py" --status-only

echo
read -r -p "Press Enter to close..."
