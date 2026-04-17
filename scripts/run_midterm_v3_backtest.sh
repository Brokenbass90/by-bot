#!/usr/bin/env bash
# =============================================================================
#  run_midterm_v3_backtest.sh
#  Full BTCETHMidtermV3 backtest on server — needs BTC+ETH kline cache.
#
#  Run on server:
#    bash scripts/run_midterm_v3_backtest.sh
#
#  Results saved to: backtest_runs/midterm_v3_*
# =============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

TAG="midterm_v3_btceth_$(date +%Y%m%d)"
SYMBOLS="BTCUSDT,ETHUSDT"
DAYS=365
END="2026-03-31"
BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-0}"
CACHE_ONLY="${CACHE_ONLY:-$BACKTEST_CACHE_ONLY}"

echo "═══════════════════════════════════════════════"
echo "  BTCETHMidtermV3 Backtest — $TAG"
echo "  Symbols: $SYMBOLS | Days: $DAYS | End: $END"
echo "═══════════════════════════════════════════════"
echo ""

# ── Test 1: v3 MACD-shorts only (baseline for v3) ─────────────────────────
echo "▶ Test 1: v3 with MACD shorts filter only (recommended config)"
MTPB3_SYMBOL_ALLOWLIST="$SYMBOLS" \
MTPB3_ALLOW_LONGS=1 \
MTPB3_ALLOW_SHORTS=1 \
MTPB3_REQUIRE_HIST_SIGN_SHORTS=1 \
MTPB3_REQUIRE_HIST_SIGN_LONGS=0 \
MTPB3_USE_RSI_FILTER=0 \
MTPB3_USE_VOL_FILTER=0 \
MTPB3_FRESH_TOUCH_BARS=5 \
MTPB3_RR=2.5 \
MTPB3_LONG_COOLDOWN_BARS=84 \
MTPB3_SHORT_COOLDOWN_BARS=84 \
MTPB3_MAX_SIGNALS_PER_DAY=1 \
MIDTERM_RISK_MULT=1.0 \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" backtest/run_portfolio.py \
  --strategies btc_eth_midterm_v3 \
  --symbols "$SYMBOLS" \
  --days $DAYS --end $END \
  --starting_equity 100 \
  --risk_pct 0.01 --max_positions 2 --leverage 3 \
  --tag "${TAG}_macd_shorts"

echo ""
echo "─────────────────────────────────────────────"

# ── Test 2: v3 with RSI (looser thresholds) ─────────────────────────────
echo "▶ Test 2: v3 with MACD shorts + RSI (loose: long<65, short>35)"
MTPB3_SYMBOL_ALLOWLIST="$SYMBOLS" \
MTPB3_ALLOW_LONGS=1 \
MTPB3_ALLOW_SHORTS=1 \
MTPB3_REQUIRE_HIST_SIGN_SHORTS=1 \
MTPB3_REQUIRE_HIST_SIGN_LONGS=0 \
MTPB3_USE_RSI_FILTER=1 \
MTPB3_RSI_LONG_MAX=65 \
MTPB3_RSI_SHORT_MIN=35 \
MTPB3_USE_VOL_FILTER=0 \
MTPB3_FRESH_TOUCH_BARS=5 \
MTPB3_RR=2.5 \
MTPB3_LONG_COOLDOWN_BARS=84 \
MTPB3_SHORT_COOLDOWN_BARS=84 \
MTPB3_MAX_SIGNALS_PER_DAY=1 \
MIDTERM_RISK_MULT=1.0 \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" backtest/run_portfolio.py \
  --strategies btc_eth_midterm_v3 \
  --symbols "$SYMBOLS" \
  --days $DAYS --end $END \
  --starting_equity 100 \
  --risk_pct 0.01 --max_positions 2 --leverage 3 \
  --tag "${TAG}_macd_rsi"

echo ""
echo "─────────────────────────────────────────────"

# ── Test 3: v3 vs v1 comparison ─────────────────────────────────────────
echo "▶ Test 3: v1 comparison baseline (same period)"
MIDTERM_RISK_MULT=1.0 \
MTPB_SYMBOL_ALLOWLIST="$SYMBOLS" \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" backtest/run_portfolio.py \
  --strategies btc_eth_midterm_pullback \
  --symbols "$SYMBOLS" \
  --days $DAYS --end $END \
  --starting_equity 100 \
  --risk_pct 0.01 --max_positions 2 --leverage 3 \
  --tag "${TAG}_v1_compare"

echo ""
echo "─────────────────────────────────────────────"

# ── Test 4: v3 in current BEAR stack ────────────────────────────────────
echo "▶ Test 4: v3 added to current bear stack (ASB1+HZBO1+Elder+ATT1)"
MTPB3_SYMBOL_ALLOWLIST="$SYMBOLS" \
MTPB3_ALLOW_LONGS=1 \
MTPB3_ALLOW_SHORTS=1 \
MTPB3_REQUIRE_HIST_SIGN_SHORTS=1 \
MTPB3_REQUIRE_HIST_SIGN_LONGS=0 \
MTPB3_USE_RSI_FILTER=0 \
MTPB3_USE_VOL_FILTER=0 \
MTPB3_FRESH_TOUCH_BARS=5 \
MTPB3_RR=2.5 \
MIDTERM_RISK_MULT=0.70 \
MTPB_VERSION=3 \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" backtest/run_portfolio.py \
  --config configs/core3_live_canary_20260411_sloped_momentum.env \
  --strategies btc_eth_midterm_v3,elder_triple_screen_v2,alt_slope_break_v1,alt_horizontal_break_v1,alt_trendline_touch_v1 \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --days $DAYS --end $END \
  --starting_equity 100 \
  --risk_pct 0.01 --max_positions 4 --leverage 3 \
  --tag "${TAG}_in_bear_stack" 2>&1 || echo "(May fail if --config not supported — run manually)"

echo ""
echo "═══════════════════════════════════════════════"
echo "  SUMMARY:"
echo ""
for d in backtest_runs/*${TAG}*/; do
    if [ -f "$d/summary.csv" ]; then
        tag_name=$(basename "$d")
        result=$(tail -1 "$d/summary.csv")
        trades=$(echo "$result" | cut -d, -f8)
        pf=$(echo "$result" | cut -d, -f10)
        pnl=$(echo "$result" | cut -d, -f9)
        echo "  $tag_name: trades=$trades PF=$pf net=$pnl"
    fi
done
echo ""
echo "  PASS criteria: trades ≥ 20, PF ≥ 1.10, net > 0"
echo "  If PASS: add to live config as MTPB_VERSION=3, ENABLE_MIDTERM_TRADING=1"
echo "═══════════════════════════════════════════════"
