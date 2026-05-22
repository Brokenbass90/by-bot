#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs runtime/equities_yf_cache

stamp="$(date -u +%Y%m%d_%H%M%S)"
log="logs/alpaca_v39_local_research_${stamp}.log"

echo "[alpaca-v39] started ${stamp} UTC" | tee -a "$log"
PYTHONDONTWRITEBYTECODE=1 python3 scripts/alpaca_v3_event_backtest.py \
  --start 2024-05-01 \
  --end 2026-05-01 \
  --capital 1000 \
  --tag "local_wide_grid_${stamp}" \
  --grid \
  --wide-grid \
  --cache-dir runtime/equities_yf_cache \
  2>&1 | tee -a "$log"
echo "[alpaca-v39] finished $(date -u +%Y%m%d_%H%M%S) UTC" | tee -a "$log"
