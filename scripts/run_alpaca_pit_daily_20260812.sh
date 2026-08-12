#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
.venv/bin/python scripts/materialize_alpaca_pit_daily.py \
  --allow-readonly-network \
  --start 2024-08-12 \
  --end 2026-08-12 \
  --target-size 1000 \
  --inactive-cap 300 \
  --throttle-seconds 12.5 \
  --min-free-gb 50

.venv/bin/python scripts/validate_alpaca_pit_daily.py
