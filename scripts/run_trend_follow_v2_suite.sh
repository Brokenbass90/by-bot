#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TS="$(date -u +%Y%m%d_%H%M%S)"
OUT="backtest_runs/trend_follow_v2_suite_${TS}"
mkdir -p "$OUT"
REP="$OUT/report.txt"

SYMS="${TF2_SYMBOLS:-BTCUSDT,ETHUSDT}"
DAYS="${TF2_DAYS:-360}"
END="${TF2_END_DATE:-2026-03-01}"
RISK="${TF2_RISK_PCT:-0.005}"
LEV="${TF2_LEVERAGE:-3}"
MAXPOS="${TF2_MAX_POSITIONS:-3}"

run_one() {
  local tag="$1" fee="$2" slip="$3"
  echo "\n>>> RUN $tag" | tee -a "$REP"
  python3 backtest/run_portfolio.py \
    --symbols "$SYMS" \
    --strategies btc_eth_trend_follow_v2 \
    --days "$DAYS" --end "$END" \
    --tag "$tag" \
    --starting_equity 100 --risk_pct "$RISK" --leverage "$LEV" --max_positions "$MAXPOS" \
    --fee_bps "$fee" --slippage_bps "$slip" | tee -a "$REP"

  local run_dir
  run_dir="$(grep 'Saved portfolio run to:' "$REP" | tail -n1 | awk -F': ' '{print $2}')"
  echo "run_dir=$run_dir" | tee -a "$REP"
  cat "$run_dir/summary.csv" | tee -a "$REP"
  python3 scripts/monthly_pnl.py "$run_dir/trades.csv" | tee -a "$REP"
}

echo "trend follow v2 suite start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee "$REP"
echo "symbols=$SYMS days=$DAYS end=$END" | tee -a "$REP"

run_one "tf2_base_${DAYS}d" 6 2
run_one "tf2_stress_${DAYS}d" 10 10

echo "\ntrend follow v2 suite done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee -a "$REP"
echo "report=$REP" | tee -a "$REP"
