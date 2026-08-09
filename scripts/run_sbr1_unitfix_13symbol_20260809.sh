#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export BACKTEST_CACHE_ONLY=1
export BACKTEST_MIN_COVERAGE_FRAC=0.99

python_bin=".venv/bin/python"
symbols="BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,LINKUSDT,DOTUSDT,AVAXUSDT,BNBUSDT,LTCUSDT,SUIUSDT"

"${python_bin}" backtest/run_portfolio.py \
  --symbols "${symbols}" \
  --strategies sloped_break_retest_v1 \
  --days 90 \
  --end 2026-06-11 \
  --starting_equity 100 \
  --risk_pct 1.0 \
  --cap_notional 30 \
  --leverage 1 \
  --max_positions 3 \
  --fee_bps 6 \
  --slippage_bps 1 \
  --entry-on-next-open \
  --cache data_cache \
  --tag SBR1-UNITFIX-12COVERED-90D-20260809
