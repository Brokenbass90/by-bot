#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="$ROOT/configs/alpaca_live_v38.env"
SSH_KEY="${ALPACA_DEPLOY_SSH_KEY:-$HOME/.ssh/by-bot}"
SERVER_TARGET="${ALPACA_DEPLOY_TARGET:-root@64.226.73.119:/root/by-bot/configs/alpaca_live_v38.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: missing $ENV_FILE" >&2
  exit 2
fi

if grep -q "PASTE_KEY_ID_HERE\\|PASTE_SECRET_KEY_HERE" "$ENV_FILE"; then
  echo "error: replace PASTE_KEY_ID_HERE and PASTE_SECRET_KEY_HERE in configs/alpaca_live_v38.env first" >&2
  exit 2
fi

if ! grep -q "^ALPACA_BASE_URL=https://api.alpaca.markets$" "$ENV_FILE"; then
  echo "error: ALPACA_BASE_URL must be https://api.alpaca.markets" >&2
  exit 2
fi

if ! grep -q "^ALPACA_SEND_ORDERS=0$" "$ENV_FILE"; then
  echo "error: keep ALPACA_SEND_ORDERS=0 for the first live-account dry-run" >&2
  exit 2
fi

chmod 600 "$ENV_FILE"
scp -p -i "$SSH_KEY" "$ENV_FILE" "$SERVER_TARGET"
echo "deployed=$SERVER_TARGET"
echo "send_orders=0"
