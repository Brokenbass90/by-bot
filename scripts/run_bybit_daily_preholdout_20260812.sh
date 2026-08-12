#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/materialize_bybit_daily_preholdout.py \
  --allow-public-network \
  --start 2023-01-01 \
  --end-exclusive 2025-10-01 \
  --min-free-gb 50 \
  --sleep-seconds 0.1
