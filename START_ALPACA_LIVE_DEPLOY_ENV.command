#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
clear

echo "Deploy Alpaca LIVE env"
echo
echo "This sends configs/alpaca_live_v38.env to the VPS."
echo "It will not print the key or secret."
echo

bash scripts/deploy_alpaca_live_v38_env.sh

echo
echo "Done. Tell Codex: env deployed."
read -r -p "Press Enter to close..."
