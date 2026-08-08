#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.tradingstation.research-station"
TEMPLATE="$ROOT/deploy/${LABEL}.plist.in"
AGENT_DIR="$HOME/Library/LaunchAgents"
TARGET="$AGENT_DIR/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$AGENT_DIR" "$ROOT/logs" "$ROOT/runtime/local_research_station"
sed "s|__ROOT__|$ROOT|g" "$TEMPLATE" > "$TARGET.tmp"
plutil -lint "$TARGET.tmp" >/dev/null
mv "$TARGET.tmp" "$TARGET"

launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
if ! launchctl bootstrap "$DOMAIN" "$TARGET"; then
  DISABLED="$TARGET.disabled"
  mv "$TARGET" "$DISABLED"
  echo "launchagent_not_installed=$DISABLED" >&2
  echo "macOS denied background access to the repository." >&2
  echo "Grant Full Disk Access to the executable used by the agent, then rerun this installer." >&2
  exit 1
fi
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"
sleep 3

if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "launchagent_loaded_but_not_visible=$TARGET" >&2
  exit 1
fi
if [[ ! -s "$ROOT/runtime/local_research_station/status.json" ]]; then
  echo "launchagent_loaded_without_status=$TARGET" >&2
  echo "Check $ROOT/logs/research_station_launchd.err.log and macOS Full Disk Access." >&2
  exit 1
fi

echo "installed=$TARGET"
echo "label=$LABEL"
echo "status=$ROOT/runtime/local_research_station/status.json"
echo "mode=research_only_no_live_orders"
