#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

python3 scripts/fetch_forex_yfinance.py \
  --pairs "${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}" \
  --period "${FX_YF_PERIOD:-60d}" \
  --interval "${FX_YF_INTERVAL:-5m}" \
  --out-dir "${FX_DATA_DIR:-data_cache/forex}"

