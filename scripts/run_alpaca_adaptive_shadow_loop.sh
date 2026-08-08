#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs runtime/equities_yf_cache
source scripts/research_loop_lock.sh
acquire_research_loop_lock "runtime/alpaca_adaptive_shadow_loop.lock" || exit 0

while true; do
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/alpaca_adaptive_shadow.py \
    --start 2025-01-01 \
    --capital "${ALPACA_ADAPTIVE_SHADOW_CAPITAL:-484}" \
    --target-alloc-pct 70 \
    --max-positions 4 \
    --preset baseline \
    --out-json runtime/alpaca_adaptive_v1_shadow_latest.json \
    --out-md runtime/alpaca_adaptive_v1_shadow_latest.md \
    >> "logs/alpaca_adaptive_shadow_${stamp}.log" 2>&1 || true
  sleep "${ALPACA_ADAPTIVE_SHADOW_POLL_SEC:-21600}"
done
