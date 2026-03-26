#!/usr/bin/env bash
set -euo pipefail

# Overnight A/B for the current production stack:
#   inplay_breakout + btc_eth_midterm_pullback
#
# Profiles:
#   1) baseline
#   2) quality gate only
#   3) allocator soft only
#   4) quality gate + allocator soft
#
# For each profile:
#   - 360d base costs
#   - 360d stress costs
#
# Output:
#   backtest_runs/live_stack_ab_<timestamp>/report.txt

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${END_DATE:-2026-03-01}"
DAYS="${DAYS:-360}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,AVAXUSDT}"
STRATEGIES="${STRATEGIES:-inplay_breakout,btc_eth_midterm_pullback}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.0}"

# quality profile (same gate as live/backtest gate)
QUALITY_MIN="${BT_BREAKOUT_QUALITY_MIN_SCORE:-0.58}"

# allocator soft profile (validated as non-aggressive profile)
ALLOCATOR_MULT_MIN="${ALLOCATOR_MULT_MIN:-0.80}"
ALLOCATOR_MULT_MAX="${ALLOCATOR_MULT_MAX:-1.20}"
ALLOC_BREAKOUT_TREND_MULT="${ALLOC_BREAKOUT_TREND_MULT:-1.08}"
ALLOC_BREAKOUT_FLAT_MULT="${ALLOC_BREAKOUT_FLAT_MULT:-0.90}"
ALLOC_MIDTERM_TREND_MULT="${ALLOC_MIDTERM_TREND_MULT:-0.92}"
ALLOC_MIDTERM_FLAT_MULT="${ALLOC_MIDTERM_FLAT_MULT:-1.08}"

RUNSET_DIR="backtest_runs/live_stack_ab_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"
touch "$REPORT"

echo "live stack A/B start: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "symbols=$SYMBOLS" | tee -a "$REPORT"
echo "strategies=$STRATEGIES" | tee -a "$REPORT"
echo "days=$DAYS end_date=$END_DATE" | tee -a "$REPORT"
echo "quality_min=$QUALITY_MIN" | tee -a "$REPORT"
echo "allocator_soft=[min=$ALLOCATOR_MULT_MIN max=$ALLOCATOR_MULT_MAX b_trend=$ALLOC_BREAKOUT_TREND_MULT b_flat=$ALLOC_BREAKOUT_FLAT_MULT m_trend=$ALLOC_MIDTERM_TREND_MULT m_flat=$ALLOC_MIDTERM_FLAT_MULT]" | tee -a "$REPORT"

run_case () {
  local profile="$1"      # baseline|quality|allocator_soft|combo
  local costs="$2"        # base|stress
  local fee="$3"
  local slip="$4"
  local q_enable="$5"     # 0|1
  local alloc_enable="$6" # 0|1
  local tag="stack_${profile}_${costs}_${DAYS}d"

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  BYBIT_DATA_POLITE_SLEEP_SEC="$POLITE_SLEEP" \
  BT_BREAKOUT_QUALITY_ENABLE="$q_enable" \
  BT_BREAKOUT_QUALITY_MIN_SCORE="$QUALITY_MIN" \
  ALLOCATOR_ENABLE="$alloc_enable" \
  ALLOCATOR_MULT_MIN="$ALLOCATOR_MULT_MIN" \
  ALLOCATOR_MULT_MAX="$ALLOCATOR_MULT_MAX" \
  ALLOC_BREAKOUT_TREND_MULT="$ALLOC_BREAKOUT_TREND_MULT" \
  ALLOC_BREAKOUT_FLAT_MULT="$ALLOC_BREAKOUT_FLAT_MULT" \
  ALLOC_MIDTERM_TREND_MULT="$ALLOC_MIDTERM_TREND_MULT" \
  ALLOC_MIDTERM_FLAT_MULT="$ALLOC_MIDTERM_FLAT_MULT" \
  python3 backtest/run_portfolio.py \
    --symbols "$SYMBOLS" \
    --strategies "$STRATEGIES" \
    --days "$DAYS" --end "$END_DATE" \
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

  local short_row
  short_row="$(tail -n 1 "$run_dir/summary.csv")"
  echo "compact=${profile},${costs},${short_row}" | tee -a "$REPORT"
}

# baseline
run_case baseline base   6  2  0 0
run_case baseline stress 10 10 0 0

# quality gate only
run_case quality base    6  2  1 0
run_case quality stress  10 10 1 0

# allocator soft only
run_case allocator_soft base   6  2  0 1
run_case allocator_soft stress 10 10 0 1

# combined profile
run_case combo base   6  2  1 1
run_case combo stress 10 10 1 1

echo "" | tee -a "$REPORT"
echo "live stack A/B done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"

