#!/usr/bin/env bash
set -euo pipefail

# One-command runner:
# 1) portfolio backtest
# 2) baselines (bounce/range/pump_fade/inplay) on the exact same symbols
# 3) simple leaderboard from portfolio trades
#
# Usage:
#   BYBIT_DATA_POLITE_SLEEP_SEC=0.8 \
#   INPLAY_REGIME=1 INPLAY_ALLOW_LONGS=0 INPLAY_ALLOW_SHORTS=1 \
#   bash scripts/run_core_suite.sh 2026-02-01 180 25 20000000

# By default we DO NOT include bounce in the portfolio mix (it has been the
# largest source of losses in recent runs). To include it:
#   CORE_STRATEGIES=inplay,pump_fade,bounce bash scripts/run_core_suite.sh ...

END_DATE="${1:-2026-02-01}"
DAYS="${2:-180}"
TOP_N="${3:-25}"
MIN_VOL="${4:-20000000}"
TAG="${5:-core_suite}"

CORE_STRATEGIES="${CORE_STRATEGIES:-inplay,pump_fade}"

python3 backtest/run_portfolio.py \
  --auto_symbols --top_n "$TOP_N" --min_volume_usd "$MIN_VOL" \
  --days "$DAYS" --end "$END_DATE" \
  --strategies "$CORE_STRATEGIES" \
  --max_positions 3 \
  --starting_equity 100 \
  --risk_pct 0.005 \
  --cap_notional 30 \
  --leverage 3 \
  --tag "$TAG"

RUN_DIR=$(ls -1dt backtest_runs/portfolio_* | head -n 1)
echo "Latest portfolio run: $RUN_DIR"

BYBIT_DATA_POLITE_SLEEP_SEC="${BYBIT_DATA_POLITE_SLEEP_SEC:-0.8}" \
  bash scripts/run_baselines_30d.sh "$RUN_DIR" "$END_DATE" 30

python3 scripts/leaderboard_trades.py "$RUN_DIR/trades.csv" || true
