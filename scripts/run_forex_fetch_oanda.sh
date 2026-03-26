#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

python3 scripts/fetch_forex_oanda.py \
  --pairs "${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}" \
  --days "${FX_DAYS:-365}" \
  --granularity "${FX_GRANULARITY:-M5}" \
  --count-per-request "${FX_COUNT_PER_REQUEST:-5000}" \
  --sleep-sec "${FX_SLEEP_SEC:-0.12}" \
  --out-dir "${FX_DATA_DIR:-data_cache/forex}" \
  --base-url "${OANDA_API_URL:-https://api-fxpractice.oanda.com}" \
  --token "${OANDA_API_TOKEN:-}"
