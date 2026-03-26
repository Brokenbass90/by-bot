#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

python3 scripts/forex_data_check.py \
  --pairs "${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}" \
  --data-dir "${FX_DATA_DIR:-data_cache/forex}" \
  --out "${FX_DATA_STATUS_OUT:-docs/forex_data_status.csv}"
