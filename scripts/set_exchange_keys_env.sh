#!/usr/bin/env bash
set -euo pipefail

# Interactive helper for the server itself.
# Run from /root/by-bot:
#   bash scripts/set_exchange_keys_env.sh
#
# It updates .env in the current directory. Secrets are not printed.

ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Run this from /root/by-bot or set ENV_FILE=/path/to/.env" >&2
  exit 1
fi

read -r -p "BINANCE_API_KEY: " BINANCE_API_KEY
read -r -s -p "BINANCE_API_SECRET: " BINANCE_API_SECRET
printf "\n"

read -r -p "BITGET_API_KEY (empty to skip): " BITGET_API_KEY
if [[ -n "$BITGET_API_KEY" ]]; then
  read -r -s -p "BITGET_API_SECRET: " BITGET_API_SECRET
  printf "\n"
  read -r -s -p "BITGET_API_PASSPHRASE: " BITGET_API_PASSPHRASE
  printf "\n"
else
  BITGET_API_SECRET=""
  BITGET_API_PASSPHRASE=""
fi

if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_API_SECRET" ]]; then
  echo "ERROR: Binance key and secret are required." >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"

{
  printf 'BINANCE_API_KEY=%s\n' "$BINANCE_API_KEY"
  printf 'BINANCE_API_SECRET=%s\n' "$BINANCE_API_SECRET"
  if [[ -n "$BITGET_API_KEY" ]]; then
    printf 'BITGET_API_KEY=%s\n' "$BITGET_API_KEY"
    printf 'BITGET_API_SECRET=%s\n' "$BITGET_API_SECRET"
    printf 'BITGET_API_PASSPHRASE=%s\n' "$BITGET_API_PASSPHRASE"
  fi
} > "$tmp"

cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"

python3 - "$tmp" "$ENV_FILE" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1])
env_path = Path(sys.argv[2])
ordered = [
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BITGET_API_KEY",
    "BITGET_API_SECRET",
    "BITGET_API_PASSPHRASE",
]

updates = {}
for raw in src.read_text(encoding="utf-8").splitlines():
    if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    key = key.strip()
    if key in ordered:
        updates[key] = value

lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)

missing = [key for key in ordered if key in updates and key not in seen]
if missing:
    if out and out[-1].strip():
        out.append("")
    out.append("# Cross-exchange arbitration read-only keys")
    for key in missing:
        out.append(f"{key}={updates[key]}")

env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

echo "Saved. Current status:"
grep -E '^(BINANCE|BITGET)_' "$ENV_FILE" | sed 's/=.*/=SET/'

