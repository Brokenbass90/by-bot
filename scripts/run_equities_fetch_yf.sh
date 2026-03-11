#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TICKERS="${EQ_TICKERS:-AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM}"
PERIOD="${EQ_YF_PERIOD:-60d}"
INTERVAL="${EQ_YF_INTERVAL:-5m}"
DATA_DIR="${EQ_DATA_DIR:-data_cache/equities}"

python3 scripts/fetch_equities_yfinance.py \
  --tickers "$TICKERS" \
  --period "$PERIOD" \
  --interval "$INTERVAL" \
  --out-dir "$DATA_DIR"
