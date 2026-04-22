#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_STAMP="${RUN_STAMP:-20260422}"

COMMON_ENV=(
  ATT1_MAX_PIVOT_AGE=12
  ATT1_MIN_PIVOTS=2
  ATT1_MIN_R2=0.9
  ATT1_PIVOT_LEFT=3
  ATT1_PIVOT_RIGHT=3
  ATT1_RSI_LONG_MAX=60
  ATT1_RSI_SHORT_MIN=45
  ATT1_TOUCH_ATR=0.35
  ENABLE_ASB1_TRADING=1
  ASB1_RISK_MULT=0.50
  ASB1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
  ASB1_SIGNAL_TF=60
  ASB1_SIGNAL_LOOKBACK=120
  ASB1_PIVOT_LEFT=3
  ASB1_PIVOT_RIGHT=3
  ASB1_MIN_PIVOTS=2
  ASB1_MAX_PIVOT_AGE=20
  ASB1_MIN_SLOPE_PCT=0.05
  ASB1_MAX_SLOPE_PCT=5.0
  ASB1_MIN_R2=0.70
  ASB1_BREAK_ATR=0.30
  ASB1_MIN_BODY_FRAC=0.40
  ASB1_RSI_SHORT_MAX=65.0
  ASB1_RSI_LONG_MIN=35.0
  ASB1_MACRO_TF=240
  ASB1_MACRO_REQUIRE_BEARISH=1
  ASB1_MACRO_REQUIRE_BULLISH=0
  ASB1_MACRO_MACD_FAST=12
  ASB1_MACRO_MACD_SLOW=26
  ASB1_MACRO_MACD_SIGNAL=9
  ASB1_SL_ATR_MULT=0.80
  ASB1_TP1_RR=1.5
  ASB1_TP2_RR=3.0
  ASB1_TP1_FRAC=0.50
  ASB1_BE_TRIGGER_RR=1.00
  ASB1_BE_LOCK_RR=0.02
  ASB1_TIME_STOP_BARS_5M=576
  ASB1_COOLDOWN_BARS_5M=72
  ASB1_ALLOW_LONGS=0
  ASB1_ALLOW_SHORTS=1
)

run_case() {
  local name="$1"
  local strategies="$2"
  local end_date="$3"
  local days="$4"
  local tag="${name}_${RUN_STAMP}"
  echo "=== [$tag] start $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
  env "${COMMON_ENV[@]}" \
    python3 backtest/run_portfolio.py \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
      --strategies "$strategies" \
      --days "$days" \
      --end "$end_date" \
      --tag "$tag" \
      --starting_equity 100 \
      --risk_pct 0.005 \
      --leverage 3 \
      --max_positions 3 \
      --fee_bps 10 \
      --slippage_bps 10
  echo "=== [$tag] done $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
}

for spec in \
  "y2025 2025-12-31 365" \
  "y2026ytd 2026-04-21 110"
do
  set -- $spec
  year_tag="$1"
  end_date="$2"
  days="$3"

  run_case "core2_att1_asb1_${year_tag}" \
    "alt_trendline_touch_v1,alt_slope_break_v1" \
    "$end_date" "$days"

  run_case "core3_att1_asb1_flat_${year_tag}" \
    "alt_trendline_touch_v1,alt_slope_break_v1,alt_resistance_fade_v1" \
    "$end_date" "$days"

  run_case "core3_att1_asb1_range_${year_tag}" \
    "alt_trendline_touch_v1,alt_slope_break_v1,alt_range_scalp_v1" \
    "$end_date" "$days"
done
