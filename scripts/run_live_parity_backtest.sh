#!/usr/bin/env bash
set -euo pipefail

# Live-parity replay for breakout+midterm.
# Goal: quickly check if "no live entries" is due to infra or strict filters.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

DAYS="${DAYS:-7}"
END_DATE="${END_DATE:-}"
AUTO_SYMBOLS="${AUTO_SYMBOLS:-1}"
TOP_N="${TOP_N:-16}"
TAG_PREFIX="${TAG_PREFIX:-live_parity}"
MIN_VOLUME_USD="${MIN_VOLUME_USD:-20000000}"
EXCLUDE_SYMBOLS="${EXCLUDE_SYMBOLS:-${BREAKOUT_SYMBOL_DENYLIST:-}}"
SYMBOLS="${SYMBOLS:-}"

STRATEGIES="${STRATEGIES:-inplay_breakout,btc_eth_midterm_pullback}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.0}"

# Keep breakout profile close to live defaults.
QUALITY_ENABLE="${QUALITY_ENABLE:-1}"
QUALITY_MIN="${QUALITY_MIN:-0.52}"
MAX_CHASE="${MAX_CHASE:-0.22}"
MAX_LATE="${MAX_LATE:-0.55}"
MIN_PULLBACK="${MIN_PULLBACK:-0.03}"
IMPULSE_ATR_MULT="${IMPULSE_ATR_MULT:-0.75}"
IMPULSE_BODY_MIN_FRAC="${IMPULSE_BODY_MIN_FRAC:-0.40}"
IMPULSE_VOL_MULT="${IMPULSE_VOL_MULT:-0.0}"
RECLAIM_ATR="${RECLAIM_ATR:-0.10}"
MAX_DIST_ATR="${MAX_DIST_ATR:-1.50}"
BUFFER_ATR="${BUFFER_ATR:-0.06}"
ALLOW_SHORTS="${ALLOW_SHORTS:-1}"
REGIME_STRICT="${REGIME_STRICT:-0}"

RUNSET_DIR="backtest_runs/live_parity_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"

echo "live parity replay start: $(date -u '+%F %T UTC')" | tee "$REPORT"
echo "days=$DAYS end_date=${END_DATE:-<auto>}" | tee -a "$REPORT"
echo "strategies=$STRATEGIES" | tee -a "$REPORT"
if [[ "$AUTO_SYMBOLS" == "1" ]]; then
  echo "universe=auto top_n=$TOP_N min_volume_usd=$MIN_VOLUME_USD exclude=${EXCLUDE_SYMBOLS:-<none>}" | tee -a "$REPORT"
else
  echo "universe=fixed symbols=${SYMBOLS:-<empty>}" | tee -a "$REPORT"
fi
echo "profile: q_min=$QUALITY_MIN impulse_atr=$IMPULSE_ATR_MULT impulse_body=$IMPULSE_BODY_MIN_FRAC max_chase=$MAX_CHASE max_late=$MAX_LATE" | tee -a "$REPORT"

run_case() {
  local costs="$1"
  local fee="$2"
  local slip="$3"
  local tag="${TAG_PREFIX}_${costs}_${DAYS}d"
  local -a args

  args=(
    --strategies "$STRATEGIES"
    --days "$DAYS"
    --tag "$tag"
    --starting_equity "$STARTING_EQUITY"
    --risk_pct "$RISK_PCT"
    --leverage "$LEVERAGE"
    --max_positions "$MAX_POSITIONS"
    --fee_bps "$fee"
    --slippage_bps "$slip"
  )

  if [[ -n "$END_DATE" ]]; then
    args+=(--end "$END_DATE")
  fi

  if [[ "$AUTO_SYMBOLS" == "1" ]]; then
    args+=(--auto_symbols --top_n "$TOP_N" --min_volume_usd "$MIN_VOLUME_USD")
    if [[ -n "$EXCLUDE_SYMBOLS" ]]; then
      args+=(--exclude_symbols "$EXCLUDE_SYMBOLS")
    fi
  else
    if [[ -z "$SYMBOLS" ]]; then
      echo "ERROR: AUTO_SYMBOLS=0 but SYMBOLS is empty" | tee -a "$REPORT"
      exit 1
    fi
    args+=(--symbols "$SYMBOLS")
  fi

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  BYBIT_DATA_POLITE_SLEEP_SEC="$POLITE_SLEEP" \
  BT_BREAKOUT_QUALITY_ENABLE="$QUALITY_ENABLE" \
  BT_BREAKOUT_QUALITY_MIN_SCORE="$QUALITY_MIN" \
  BREAKOUT_MAX_CHASE_PCT="$MAX_CHASE" \
  BREAKOUT_MAX_LATE_VS_REF_PCT="$MAX_LATE" \
  BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT="$MIN_PULLBACK" \
  BREAKOUT_IMPULSE_ATR_MULT="$IMPULSE_ATR_MULT" \
  BREAKOUT_IMPULSE_BODY_MIN_FRAC="$IMPULSE_BODY_MIN_FRAC" \
  BREAKOUT_IMPULSE_VOL_MULT="$IMPULSE_VOL_MULT" \
  BREAKOUT_RECLAIM_ATR="$RECLAIM_ATR" \
  BREAKOUT_MAX_DIST_ATR="$MAX_DIST_ATR" \
  BREAKOUT_BUFFER_ATR="$BUFFER_ATR" \
  BREAKOUT_ALLOW_SHORTS="$ALLOW_SHORTS" \
  BREAKOUT_REGIME_STRICT="$REGIME_STRICT" \
  python3 backtest/run_portfolio.py "${args[@]}" | tee -a "$REPORT"

  local run_dir
  run_dir="$(ls -1dt backtest_runs/*"${tag}" 2>/dev/null | head -n 1)"
  if [[ -z "$run_dir" ]]; then
    echo "FAILED: run dir not found for $tag" | tee -a "$REPORT"
    return
  fi
  echo "run_dir=$run_dir" | tee -a "$REPORT"
  cat "$run_dir/summary.csv" | tee -a "$REPORT"
  python3 scripts/monthly_pnl.py "$run_dir/trades.csv" | tee -a "$REPORT"
}

run_case base 6 2
run_case stress 10 10

echo "" | tee -a "$REPORT"
echo "live parity replay done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"
