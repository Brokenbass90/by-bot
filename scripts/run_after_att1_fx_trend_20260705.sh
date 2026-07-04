#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="logs/fx_h1_trend_after_att1_20260705"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_${STAMP}.log"

{
  echo "[after-att1-fx] start_utc=$(date -u +%FT%TZ)"
  echo "[after-att1-fx] waiting for screen att1_universe_20260705"
  while (screen -ls 2>/dev/null || true) | grep -q "att1_universe_20260705"; do
    sleep 60
  done

  echo "[after-att1-fx] att1 universe finished; launching FX H1 trend family"
  .venv/bin/python scripts/run_fx_native_harness.py \
    --data-dir data_cache/forex_1h \
    --pairs EURUSD,GBPUSD,USDJPY \
    --setups trend_pullback,session_breakout_retest \
    --outdir reports/research/fx_h1_trend_after_att1_20260705 \
    --interval-min 60 \
    --coverage-interval-min 60 \
    --min-coverage 0.99 \
    --max-gap-bars 24 \
    --max-flat-frac 0.05 \
    --min-coverage-bars 1000 \
    --fee-bps 1.0 \
    --slippage-bps 0.5

  echo "[after-att1-fx] done_utc=$(date -u +%FT%TZ)"
} 2>&1 | tee "$LOG_FILE"
