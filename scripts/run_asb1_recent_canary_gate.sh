#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

run_case() {
  local name="$1"
  local end_date="$2"
  local days="$3"
  local tag="${name}_20260422"
  echo "=== [$tag] start $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
  env \
    ENABLE_ASB1_TRADING=1 \
    ASB1_RISK_MULT=0.50 \
    ASB1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
    ASB1_SIGNAL_TF=60 \
    ASB1_SIGNAL_LOOKBACK=120 \
    ASB1_PIVOT_LEFT=3 \
    ASB1_PIVOT_RIGHT=3 \
    ASB1_MIN_PIVOTS=2 \
    ASB1_MAX_PIVOT_AGE=20 \
    ASB1_MIN_SLOPE_PCT=0.05 \
    ASB1_MAX_SLOPE_PCT=5.0 \
    ASB1_MIN_R2=0.70 \
    ASB1_BREAK_ATR=0.30 \
    ASB1_MIN_BODY_FRAC=0.40 \
    ASB1_RSI_SHORT_MAX=65.0 \
    ASB1_RSI_LONG_MIN=35.0 \
    ASB1_MACRO_TF=240 \
    ASB1_MACRO_REQUIRE_BEARISH=1 \
    ASB1_MACRO_REQUIRE_BULLISH=0 \
    ASB1_MACRO_MACD_FAST=12 \
    ASB1_MACRO_MACD_SLOW=26 \
    ASB1_MACRO_MACD_SIGNAL=9 \
    ASB1_SL_ATR_MULT=0.80 \
    ASB1_TP1_RR=1.5 \
    ASB1_TP2_RR=3.0 \
    ASB1_TP1_FRAC=0.50 \
    ASB1_BE_TRIGGER_RR=1.00 \
    ASB1_BE_LOCK_RR=0.02 \
    ASB1_TIME_STOP_BARS_5M=576 \
    ASB1_COOLDOWN_BARS_5M=72 \
    ASB1_ALLOW_LONGS=0 \
    ASB1_ALLOW_SHORTS=1 \
    python3 backtest/run_portfolio.py \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
      --strategies alt_slope_break_v1 \
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

run_case "asb1_y2025_recent_gate" "2025-12-31" "365"
run_case "asb1_y2026ytd_recent_gate" "2026-04-21" "110"
