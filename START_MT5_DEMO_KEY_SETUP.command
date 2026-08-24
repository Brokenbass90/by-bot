#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
clear

echo "MT5 / Bullwaves DEMO key setup"
echo
echo "Generate a new MCP token inside MetaTrader 5 first."
echo "The token will not be shown while typing or pasted into Git."
echo "This shortcut does not connect, trade, or enable execution."
echo

bash scripts/setup_mt5_demo_env.sh

echo
echo "Done. You can close this window."
read -r -p "Press Enter to close..."
