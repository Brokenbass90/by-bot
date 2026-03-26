#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

SYMBOL="${FX_SYMBOL:-EURUSD}"
CSV_PATH="${FX_CSV_PATH:-data_cache/forex/${SYMBOL}_M5.csv}"
TAG="${FX_TAG:-pilot_$(date -u +%Y%m%d_%H%M%S)}"
SPREAD="${FX_SPREAD_PIPS:-1.2}"
SWAP_LONG="${FX_SWAP_LONG_PIPS_DAY:--0.2}"
SWAP_SHORT="${FX_SWAP_SHORT_PIPS_DAY:--0.2}"

if [[ ! -f "$CSV_PATH" ]]; then
  echo "Missing CSV: $CSV_PATH"
  echo "Expected columns: ts,o,h,l,c,v (or timestamp,open,high,low,close,volume)"
  exit 1
fi

python3 scripts/run_forex_backtest.py \
  --symbol "$SYMBOL" \
  --csv "$CSV_PATH" \
  --tag "$TAG" \
  --spread_pips "$SPREAD" \
  --swap_long "$SWAP_LONG" \
  --swap_short "$SWAP_SHORT"

