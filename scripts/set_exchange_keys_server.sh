#!/usr/bin/env bash
set -euo pipefail

# Safely write Binance/Bitget read-only keys to the server .env.
# The script never prints secret values and removes temporary files.

SERVER="${SERVER:-root@64.226.73.119}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/by-bot}"
REMOTE_DIR="${REMOTE_DIR:-/root/by-bot}"

read -r -p "BINANCE_API_KEY: " BINANCE_API_KEY
read -r -s -p "BINANCE_API_SECRET: " BINANCE_API_SECRET
printf "\n"
read -r -p "BITGET_API_KEY (empty to skip): " BITGET_API_KEY
if [[ -n "${BITGET_API_KEY}" ]]; then
  read -r -s -p "BITGET_API_SECRET: " BITGET_API_SECRET
  printf "\n"
  read -r -s -p "BITGET_API_PASSPHRASE: " BITGET_API_PASSPHRASE
  printf "\n"
else
  BITGET_API_SECRET=""
  BITGET_API_PASSPHRASE=""
fi

if [[ -z "${BINANCE_API_KEY}" || -z "${BINANCE_API_SECRET}" ]]; then
  echo "ERROR: Binance key and secret are required for this step." >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"

{
  printf 'BINANCE_API_KEY=%s\n' "$BINANCE_API_KEY"
  printf 'BINANCE_API_SECRET=%s\n' "$BINANCE_API_SECRET"
  if [[ -n "${BITGET_API_KEY}" ]]; then
    printf 'BITGET_API_KEY=%s\n' "$BITGET_API_KEY"
    printf 'BITGET_API_SECRET=%s\n' "$BITGET_API_SECRET"
    printf 'BITGET_API_PASSPHRASE=%s\n' "$BITGET_API_PASSPHRASE"
  fi
} > "$tmp"

remote_tmp="${REMOTE_DIR}/.exchange_keys_update_$(date +%Y%m%d_%H%M%S).tmp"

scp -q -i "$SSH_KEY" "$tmp" "$SERVER:$remote_tmp"

ssh -i "$SSH_KEY" "$SERVER" "cd '$REMOTE_DIR' && chmod 600 '$remote_tmp' && cp .env .env.backup.\$(date +%Y%m%d_%H%M%S) && python3 - '$remote_tmp' .env <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1])
env_path = Path(sys.argv[2])
ordered = [
    'BINANCE_API_KEY',
    'BINANCE_API_SECRET',
    'BITGET_API_KEY',
    'BITGET_API_SECRET',
    'BITGET_API_PASSPHRASE',
]

updates = {}
for raw in src.read_text(encoding='utf-8').splitlines():
    if not raw.strip() or raw.lstrip().startswith('#') or '=' not in raw:
        continue
    k, v = raw.split('=', 1)
    k = k.strip()
    if k in ordered:
        updates[k] = v

lines = env_path.read_text(encoding='utf-8', errors='ignore').splitlines() if env_path.exists() else []
seen = set()
out = []
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key = line.split('=', 1)[0].strip()
        if key in updates:
            out.append(f'{key}={updates[key]}')
            seen.add(key)
            continue
    out.append(line)

missing = [k for k in ordered if k in updates and k not in seen]
if missing:
    if out and out[-1].strip():
        out.append('')
    out.append('# Cross-exchange arbitration read-only keys')
    for key in missing:
        out.append(f'{key}={updates[key]}')

env_path.write_text('\n'.join(out) + '\n', encoding='utf-8')
src.unlink(missing_ok=True)
PY
grep -E '^(BINANCE|BITGET)_' .env | sed 's/=.*/=SET/'
systemctl restart trading-journal-web.service || true"

echo "Done. Secrets were written to $SERVER:$REMOTE_DIR/.env and were not printed."

