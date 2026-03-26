#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${BTC_BENCH_END_DATE:-2026-02-24}"
DAYS="${BTC_BENCH_DAYS:-360}"
STAMP="${BTC_BENCH_STAMP:-$(date -u +%Y%m%d_%H%M%S)}"

export BTCC1_ALLOW_LONGS=1
export BTCC1_ALLOW_SHORTS=0
export BTCC1_TRAIL_ATR_MULT=0
export BTCC1_TP1_RR=0.8
export BTCC1_TP2_RR=2.2
export BTCC1_TP1_FRAC=0.70
export BTCC1_TIME_STOP_BARS_5M=864
export BTCC1_REGIME_MAX_GAP_PCT=4.0
export BTCC1_REGIME_MAX_SLOPE_PCT=2.4

export BTCR1_ALLOW_LONGS=0
export BTCR1_ALLOW_SHORTS=1

run_case() {
  local tag="$1"
  local strategies="$2"
  shift 2
  "$@" python3 backtest/run_portfolio.py \
    --symbols BTCUSDT \
    --strategies "$strategies" \
    --days "$DAYS" \
    --end "$END_DATE" \
    --tag "$tag"
}

run_case "btc_bench_winner_base_${STAMP}" "btc_cycle_pullback_v1,btc_regime_retest_v1" env
run_case "btc_bench_winner_stress_${STAMP}" "btc_cycle_pullback_v1,btc_regime_retest_v1" \
  env STRESS_SLIPPAGE_BPS=12 STRESS_FEE_MULT=1.5 STRESS_FILL_PENALTY_PCT=0.05

export BTCRF1_ALLOW_LONGS=1
export BTCRF1_REGIME_MIN_GAP_PCT=0.35
export BTCRF1_REGIME_MAX_GAP_PCT=1.60
export BTCRF1_REGIME_SLOPE_MIN_PCT=0.05
export BTCRF1_REGIME_SLOPE_MAX_PCT=1.40
export BTCRF1_MIN_PULLBACK_PCT=0.20
export BTCRF1_MAX_PULLBACK_PCT=1.30
export BTCRF1_BREAKOUT_BUFFER_PCT=0.03
export BTCRF1_HOLD_ABOVE_EMA_PCT=-0.20

run_case "btc_bench_winner_earlyflip_base_${STAMP}" "btc_cycle_pullback_v1,btc_regime_flip_continuation_v1,btc_regime_retest_v1" env
run_case "btc_bench_winner_earlyflip_stress_${STAMP}" "btc_cycle_pullback_v1,btc_regime_flip_continuation_v1,btc_regime_retest_v1" \
  env STRESS_SLIPPAGE_BPS=12 STRESS_FEE_MULT=1.5 STRESS_FILL_PENALTY_PCT=0.05

echo "Finished BTC benchmark matrix stamp=${STAMP}"
