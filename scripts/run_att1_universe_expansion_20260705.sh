#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SYMBOLS="DOGEUSDT,XRPUSDT,AVAXUSDT,ATOMUSDT,BNBUSDT,BCHUSDT,XLMUSDT,1000PEPEUSDT,HYPEUSDT,TAOUSDT,ONDOUSDT"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="logs/att1_universe_expansion_20260705"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_${STAMP}.log"

{
  echo "[att1-universe] start_utc=$(date -u +%FT%TZ)"
  echo "[att1-universe] symbols=${SYMBOLS}"
  echo "[att1-universe] prefetch 5m 370d ending 2026-07-04"
  .venv/bin/python backtest/prefetch_klines.py \
    --symbols "$SYMBOLS" \
    --days 370 \
    --end 2026-07-04 \
    --cache data_cache \
    --polite_sleep_sec 0.15

  echo "[att1-universe] base cost 6/2"
  .venv/bin/python scripts/run_strategy_autoresearch.py \
    --spec configs/autoresearch/att1_short_r001_universe_expansion_20260705_base.json \
    --jobs 1

  echo "[att1-universe] stress cost 10/5"
  .venv/bin/python scripts/run_strategy_autoresearch.py \
    --spec configs/autoresearch/att1_short_r001_universe_expansion_20260705_stress.json \
    --jobs 1

  echo "[att1-universe] done_utc=$(date -u +%FT%TZ)"
} 2>&1 | tee "$LOG_FILE"
