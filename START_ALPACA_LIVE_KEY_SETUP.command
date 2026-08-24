#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
clear

echo "Alpaca LIVE key setup"
echo
echo "This will ask for:"
echo "1) Alpaca LIVE API key ID"
echo "2) Alpaca LIVE API secret key"
echo
echo "The secret will NOT be shown while typing/pasting."
echo "Do not edit code files manually."
echo

bash scripts/setup_alpaca_live_v38_env.sh

echo
echo "Done. You can close this window."
read -r -p "Press Enter to close..."
