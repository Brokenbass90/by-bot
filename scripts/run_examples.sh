#!/usr/bin/env bash
set -euo pipefail

# Run a few example backtests and write CSVs to backtest_results/
# Usage:
#   bash scripts/run_examples.sh

# shellcheck disable=SC1091
source .venv/bin/activate

END_DATE="${1:-2026-01-25}"

echo "Running examples ending at ${END_DATE} (UTC window)..."
echo

# 1) InPlay: use many liquid alts; exclude BTC/ETH because they rarely fit this pattern.
BT_TRACE=0 python -m backtest.run_month       --days 30 --end "${END_DATE}"       --auto_symbols --min_volume_usd 3000000 --top_n 80       --exclude_symbols BTCUSDT,ETHUSDT       --strategies inplay       --starting_equity 100 --leverage 3 --max_positions 3       --fee_model bybit --cap_notional 0

echo
# 2) Range: top 30 symbols, 60 days window.
BT_TRACE=0 python -m backtest.run_month       --days 60 --end "${END_DATE}"       --auto_symbols --min_volume_usd 20000000 --top_n 30       --strategies range       --starting_equity 100 --leverage 3 --max_positions 3       --fee_model bybit --cap_notional 0

echo
# 3) Bounce: top 30 symbols, 60 days window.
BT_TRACE=0 python -m backtest.run_month       --days 60 --end "${END_DATE}"       --auto_symbols --min_volume_usd 20000000 --top_n 30       --strategies bounce       --starting_equity 100 --leverage 3 --max_positions 3       --fee_model bybit --cap_notional 0

echo
# 4) Pump-fade: top 100 symbols, 30 days window.
BT_TRACE=0 python -m backtest.run_month       --days 30 --end "${END_DATE}"       --auto_symbols --min_volume_usd 3000000 --top_n 100       --strategies pump_fade       --starting_equity 100 --leverage 3 --max_positions 3       --fee_model bybit --cap_notional 0

echo
echo "Done. See: backtest_results/"
