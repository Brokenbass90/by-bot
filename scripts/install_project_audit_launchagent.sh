#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.tradingstation.project-audit"
TEMPLATE="$ROOT/deploy/${LABEL}.plist.in"
AGENT_DIR="$HOME/Library/LaunchAgents"
TARGET="$AGENT_DIR/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$AGENT_DIR" "$ROOT/logs"
sed "s|__ROOT__|$ROOT|g" "$TEMPLATE" > "$TARGET.tmp"
plutil -lint "$TARGET.tmp" >/dev/null
mv "$TARGET.tmp" "$TARGET"

launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
if ! launchctl bootstrap "$DOMAIN" "$TARGET"; then
  DISABLED="$TARGET.disabled"
  mv "$TARGET" "$DISABLED"
  echo "launchagent_not_installed=$DISABLED" >&2
  echo "macOS denied background access. Grant Full Disk Access or keep the screen supervisor running while the Mac is awake." >&2
  exit 1
fi
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo "installed=$TARGET"
echo "label=$LABEL"
echo "interval_sec=21600"
echo "mode=proposal_only_no_live_mutation"
