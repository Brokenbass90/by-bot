#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TICKERS="${EQ_TICKERS:-AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM}"
DATA_DIR="${EQ_DATA_DIR:-data_cache/equities}"

python3 scripts/equities_data_check.py \
  --tickers "$TICKERS" \
  --data-dir "$DATA_DIR" \
  --out "docs/equities_data_status.csv"
