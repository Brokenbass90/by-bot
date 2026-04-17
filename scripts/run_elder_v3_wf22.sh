#!/usr/bin/env bash
# =============================================================================
#  run_elder_v3_wf22.sh
#  Durable WF-22 runner for elder_triple_screen_v3.
#
#  Run on server:
#    bash scripts/run_elder_v3_wf22.sh
#
#  Optional env:
#    TAG_BASE=elder_v3_wf22_20260417
#    SYMBOLS=BTCUSDT,ETHUSDT
#    END=2024-12-31
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

TAG_BASE="${TAG_BASE:-elder_v3_wf22_$(date +%Y%m%d)}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT}"
END="${END:-2024-12-31}"
WF_TOTAL_DAYS="${WF_TOTAL_DAYS:-360}"
WF_WINDOW_DAYS="${WF_WINDOW_DAYS:-45}"
WF_STEP_DAYS="${WF_STEP_DAYS:-15}"
WF_WORKERS="${WF_WORKERS:-1}"
WF_TIMEOUT_SEC="${WF_TIMEOUT_SEC:-900}"
BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-0}"
CACHE_ONLY="${CACHE_ONLY:-$BACKTEST_CACHE_ONLY}"

echo "═══════════════════════════════════════════════"
echo "  Elder V3 WF-22 Validation — $TAG_BASE"
echo "  Symbols: $SYMBOLS | End: $END"
echo "═══════════════════════════════════════════════"
echo ""

ETS3_SYMBOL_ALLOWLIST="$SYMBOLS" \
BACKTEST_CACHE_ONLY="$BACKTEST_CACHE_ONLY" CACHE_ONLY="$CACHE_ONLY" \
"$PYTHON_BIN" scripts/run_generic_wf.py \
  --strategy elder_triple_screen_v3 \
  --symbols "$SYMBOLS" \
  --tag "$TAG_BASE" \
  --end "$END" \
  --total_days "$WF_TOTAL_DAYS" \
  --window_days "$WF_WINDOW_DAYS" \
  --step_days "$WF_STEP_DAYS" \
  --workers "$WF_WORKERS" \
  --timeout_sec "$WF_TIMEOUT_SEC"
