#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs/research"
mkdir -p "$LOG_DIR"

RUN_STAMP="20260421"

run_case() {
  local name="$1"
  local strategies="$2"
  local symbols="$3"
  local end_date="$4"
  local days="$5"
  shift 5

  local tag="${name}_${RUN_STAMP}"
  echo ""
  echo "=== [$tag] start $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
  env "$@" \
    python3 backtest/run_portfolio.py \
      --symbols "$symbols" \
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
  echo "=== [$tag] done  $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
}

# 2022 / 2023 / 2024 / 2025 / 2026 YTD
for spec in \
  "y2022 2022-12-31 365" \
  "y2023 2023-12-31 365" \
  "y2024 2024-12-31 366" \
  "y2025 2025-12-31 365" \
  "y2026ytd 2026-04-21 110"
do
  set -- $spec
  year_tag="$1"
  end_date="$2"
  days="$3"

  run_case \
    "att1_${year_tag}" \
    "alt_trendline_touch_v1" \
    "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT" \
    "$end_date" \
    "$days" \
    ATT1_MAX_PIVOT_AGE=12 \
    ATT1_MIN_PIVOTS=2 \
    ATT1_MIN_R2=0.9 \
    ATT1_PIVOT_LEFT=3 \
    ATT1_PIVOT_RIGHT=3 \
    ATT1_RSI_LONG_MAX=60 \
    ATT1_RSI_SHORT_MIN=45 \
    ATT1_TOUCH_ATR=0.35

  run_case \
    "breakdown_v1_${year_tag}" \
    "alt_inplay_breakdown_v1" \
    "BTCUSDT,ETHUSDT,SOLUSDT" \
    "$end_date" \
    "$days" \
    BREAKDOWN_LOOKBACK_H=36 \
    BREAKDOWN_MIN_BREAK_ATR=0.15 \
    BREAKDOWN_RSI_MAX=50 \
    BREAKDOWN_SL_ATR=1.4 \
    BREAKDOWN_RR=2.0 \
    BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT

  run_case \
    "core4_${year_tag}" \
    "alt_trendline_touch_v1,alt_inplay_breakdown_v1,alt_resistance_fade_v1,alt_range_scalp_v1" \
    "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT" \
    "$end_date" \
    "$days" \
    ATT1_MAX_PIVOT_AGE=12 \
    ATT1_MIN_PIVOTS=2 \
    ATT1_MIN_R2=0.9 \
    ATT1_PIVOT_LEFT=3 \
    ATT1_PIVOT_RIGHT=3 \
    ATT1_RSI_LONG_MAX=60 \
    ATT1_RSI_SHORT_MIN=45 \
    ATT1_TOUCH_ATR=0.35 \
    BREAKDOWN_LOOKBACK_H=36 \
    BREAKDOWN_MIN_BREAK_ATR=0.15 \
    BREAKDOWN_RSI_MAX=50 \
    BREAKDOWN_SL_ATR=1.4 \
    BREAKDOWN_RR=2.0 \
    BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT
done

echo ""
echo "All runs completed at $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
