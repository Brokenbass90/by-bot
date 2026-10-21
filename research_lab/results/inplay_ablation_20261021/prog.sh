#!/bin/bash
cd ~/irv4
export BACKTEST_CACHE_ONLY=1 IRV4_ALLOW_LONG=0 IRV4_ALLOW_SHORT=1 IRV4_USE_RETEST_QUALITY=1 IRV4_USE_LEVEL_ENTRY=1 IRV4_USE_RANGE_FILTER=0 IRV4_USE_ELDER_FILTER=0 IRV4_USE_BREAKOUT_CONFIRM=0 IRV4_ENABLE_SETUP_B=1 IRV4_ADAPTIVE=0 IRV4_MIN_STOP_PCT=0.0005 IRV4_MAX_STOP_PCT=0.20 PYTHONPATH=~/irv4
TAG=$1 DAYS=$2 END=$3; export IRV4_TP_RR=$4 IRV4_RETEST_MIN_QUALITY=$5 IRV4_LEVEL_ENTRY_VALIDITY_BARS=$6 IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=$7; SYM=$8; shift 8
FEE=${FEE:-6}; SLIP=${SLIP:-2}
for kv in "$@"; do export "$kv"; done
python3 backtest/run_portfolio.py --symbols $SYM --strategies inplay_retest_v4 --days $DAYS --end $END --tag $TAG --starting_equity 100 --risk_pct 0.005 --leverage 1 --max_positions 2 --fee_bps $FEE --slippage_bps $SLIP --entry-on-next-open >/dev/null 2>&1
tail -1 $(ls -d backtest_runs/portfolio_*_$TAG | tail -1)/summary.csv
