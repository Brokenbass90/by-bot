#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TICKERS="${EQ_TICKERS:-AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM}"
LIMIT="${EQ_EARNINGS_LIMIT:-24}"
OUT_CSV="${EQ_EARNINGS_OUT_CSV:-data_cache/equities/earnings_dates.csv}"

python3 scripts/fetch_equities_earnings_yfinance.py \
  --tickers "$TICKERS" \
  --limit "$LIMIT" \
  --out-csv "$OUT_CSV"
