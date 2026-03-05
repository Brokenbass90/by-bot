#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

python3 scripts/fetch_forex_dukascopy.py \
  --pairs "${FX_PAIRS:-EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY}" \
  --days "${FX_DUKA_DAYS:-180}" \
  --from-utc "${FX_DUKA_FROM_UTC:-}" \
  --to-utc "${FX_DUKA_TO_UTC:-}" \
  --out-dir "${FX_DATA_DIR:-data_cache/forex}" \
  --sleep-sec "${FX_DUKA_SLEEP_SEC:-0.02}" \
  --timeout-sec "${FX_DUKA_TIMEOUT_SEC:-12}" \
  --retries "${FX_DUKA_RETRIES:-1}" \
  --max-hours "${FX_DUKA_MAX_HOURS:-0}"
