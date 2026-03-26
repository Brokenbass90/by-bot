#!/usr/bin/env bash
set -euo pipefail

# Overnight A/B backtests for inplay_breakout:
# - baseline (no quality gate)
# - quality-gated (same logic as live quality score)
#
# Produces:
#   backtest_runs/quality_ab_<timestamp>/report.txt
# with links to run folders and monthly PnL tables.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${END_DATE:-2026-02-25}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,AVAXUSDT}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.5}"

QUALITY_MIN="${BT_BREAKOUT_QUALITY_MIN_SCORE:-0.58}"

RUNSET_DIR="backtest_runs/quality_ab_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"
touch "$REPORT"

echo "quality A/B start: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "symbols=$SYMBOLS" | tee -a "$REPORT"
echo "quality_min=$QUALITY_MIN" | tee -a "$REPORT"

run_case () {
  local mode="$1"   # baseline|gated
  local profile="$2" # base|stress
  local days="$3"
  local fee="$4"
  local slip="$5"
  local gate_enable="$6"
  local tag="iqab_${mode}_${profile}_${days}d"

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  BYBIT_DATA_POLITE_SLEEP_SEC="$POLITE_SLEEP" \
  BT_BREAKOUT_QUALITY_ENABLE="$gate_enable" \
  BT_BREAKOUT_QUALITY_MIN_SCORE="$QUALITY_MIN" \
  python3 backtest/run_portfolio.py \
    --symbols "$SYMBOLS" \
    --strategies inplay_breakout \
    --days "$days" --end "$END_DATE" \
    --tag "$tag" \
    --starting_equity "$STARTING_EQUITY" \
    --risk_pct "$RISK_PCT" \
    --leverage "$LEVERAGE" \
    --max_positions "$MAX_POSITIONS" \
    --fee_bps "$fee" \
    --slippage_bps "$slip" | tee -a "$REPORT"

  local run_dir
  run_dir="$(ls -1dt backtest_runs/*"${tag}" | head -n 1)"
  echo "run_dir=$run_dir" | tee -a "$REPORT"
  cat "$run_dir/summary.csv" | tee -a "$REPORT"
  python3 scripts/monthly_pnl.py "$run_dir/trades.csv" | tee -a "$REPORT"
}

# 180d quick confirmation
run_case baseline base   180 6  2  0
run_case baseline stress 180 10 10 0
run_case gated    base   180 6  2  1
run_case gated    stress 180 10 10 1

# 360d primary decision runs
run_case baseline base   360 6  2  0
run_case baseline stress 360 10 10 0
run_case gated    base   360 6  2  1
run_case gated    stress 360 10 10 1

echo "" | tee -a "$REPORT"
echo "quality A/B done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"

