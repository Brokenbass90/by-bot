#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec >> logs/rmr1_major8_prefilter_20260812.log 2>&1

DATA_ROOT="research_lab/data/bybit_major8_m5_preholdout_20240301_20250930"
RESULT_ROOT="research_lab/results/rmr1_major8_cost_prefilter_20260812"
SYMBOLS="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT,SUIUSDT,AVAXUSDT"

mkdir -p "$DATA_ROOT/ETHUSDT" "$RESULT_ROOT"
if [[ ! -s "$DATA_ROOT/ETHUSDT/ETHUSDT.json" ]]; then
  cp research_lab/data/bybit_eth_m5_preholdout_20240301_20250930/ETHUSDT.json \
    "$DATA_ROOT/ETHUSDT/ETHUSDT.json"
fi

for symbol in BTCUSDT ETHUSDT SOLUSDT LINKUSDT ADAUSDT DOTUSDT SUIUSDT AVAXUSDT; do
  while [[ ! -s "$DATA_ROOT/$symbol/$symbol.json" ]]; do
    sleep 30
  done
done

if [[ ! -s "$RESULT_ROOT/run_passport.json" ]]; then
  .venv/bin/python research_lab/run_passport.py \
    --spec research_lab/prereg/RMR1_MAJOR8_COST_PREFILTER_20260812.json \
    --output "$RESULT_ROOT/run_passport.json"
fi

for cost in 16 8; do
  .venv/bin/python scripts/backtest_candidates.py \
    --strategy rmr1 --symbols "$SYMBOLS" --input-root "$DATA_ROOT" \
    --fee-rt-bps "$cost" --time-stop 96 \
    --result-out "$RESULT_ROOT/rmr1_cost${cost}.json"
done

.venv/bin/python scripts/validate_candidate_prefilter.py \
  --passport "$RESULT_ROOT/run_passport.json" \
  --result "$RESULT_ROOT/rmr1_cost16.json" \
  --result "$RESULT_ROOT/rmr1_cost8.json" \
  --output "$RESULT_ROOT/validation_receipt.json"

echo "rmr1_major8_prefilter_complete=1"
