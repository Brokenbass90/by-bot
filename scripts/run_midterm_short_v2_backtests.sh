#!/usr/bin/env bash
# =============================================================================
#  run_midterm_short_v2_backtests.sh
#  Annual + WF validation runner for btc_eth_midterm_short_v2.
#
#  Run on server:
#    bash scripts/run_midterm_short_v2_backtests.sh
#
#  Optional env:
#    TAG_BASE=midterm_short_v2_20260417
#    SYMBOLS=BTCUSDT,ETHUSDT
#    END=2024-12-31
#    DAYS=1095
#    WF_TOTAL_DAYS=360
#    WF_WINDOW_DAYS=45
#    WF_STEP_DAYS=15
#    WF_WORKERS=1
#    WF_TIMEOUT_SEC=900
# =============================================================================
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

TAG_BASE="${TAG_BASE:-midterm_short_v2_$(date +%Y%m%d)}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT}"
END="${END:-2024-12-31}"
DAYS="${DAYS:-1095}"
WF_TOTAL_DAYS="${WF_TOTAL_DAYS:-360}"
WF_WINDOW_DAYS="${WF_WINDOW_DAYS:-45}"
WF_STEP_DAYS="${WF_STEP_DAYS:-15}"
WF_WORKERS="${WF_WORKERS:-1}"
WF_TIMEOUT_SEC="${WF_TIMEOUT_SEC:-900}"
BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-0}"
CACHE_ONLY="${CACHE_ONLY:-$BACKTEST_CACHE_ONLY}"

ANNUAL_TAG="${TAG_BASE}_annual"
WF_TAG="${TAG_BASE}_wf22"

echo "═══════════════════════════════════════════════"
echo "  Midterm Short V2 Validation — $TAG_BASE"
echo "  Symbols: $SYMBOLS | End: $END | Annual days: $DAYS"
echo "═══════════════════════════════════════════════"
echo ""

echo "▶ Annual backtest"
MTSV2_SYMBOL_ALLOWLIST="$SYMBOLS" \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" backtest/run_portfolio.py \
  --strategies btc_eth_midterm_short_v2 \
  --symbols "$SYMBOLS" \
  --days "$DAYS" --end "$END" \
  --starting_equity 100 \
  --risk_pct 0.01 --max_positions 2 --leverage 1 \
  --fee_bps 6 --slippage_bps 2 \
  --tag "$ANNUAL_TAG"

echo ""
echo "─────────────────────────────────────────────"
echo "▶ WF-22 validation"
MTSV2_SYMBOL_ALLOWLIST="$SYMBOLS" \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" scripts/run_generic_wf.py \
  --strategy btc_eth_midterm_short_v2 \
  --symbols "$SYMBOLS" \
  --tag "$WF_TAG" \
  --end "$END" \
  --total_days "$WF_TOTAL_DAYS" \
  --window_days "$WF_WINDOW_DAYS" \
  --step_days "$WF_STEP_DAYS" \
  --workers "$WF_WORKERS" \
  --timeout_sec "$WF_TIMEOUT_SEC"

echo ""
echo "═══════════════════════════════════════════════"
echo "  SUMMARY:"
for d in backtest_runs/*"${TAG_BASE}"*/; do
    [ -f "$d/summary.csv" ] || continue
    tag_name="$(basename "$d")"
    result="$(tail -1 "$d/summary.csv")"
    trades="$(echo "$result" | cut -d, -f8)"
    pf="$(echo "$result" | cut -d, -f10)"
    pnl="$(echo "$result" | cut -d, -f9)"
    echo "  $tag_name: trades=$trades PF=$pf net=$pnl"
done
echo "═══════════════════════════════════════════════"
