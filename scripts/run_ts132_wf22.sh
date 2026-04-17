#!/usr/bin/env bash
# =============================================================================
#  run_ts132_wf22.sh
#  Durable WF-22 runner for triple_screen_v132 (TS132).
#
#  Run on server:
#    bash scripts/run_ts132_wf22.sh
#
#  Optional env:
#    TAG_BASE=ts132_wf22_20260417
#    SYMBOLS=BTCUSDT,ETHUSDT,AVAXUSDT
#    END=2026-04-01
#    WF_TOTAL_DAYS=360
#    WF_WINDOW_DAYS=45
#    WF_STEP_DAYS=15
#    WF_WORKERS=2
#    WF_TIMEOUT_SEC=900
# =============================================================================
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

TAG_BASE="${TAG_BASE:-ts132_wf22_$(date +%Y%m%d)}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,AVAXUSDT}"
END="${END:-2026-04-01}"
WF_TOTAL_DAYS="${WF_TOTAL_DAYS:-360}"
WF_WINDOW_DAYS="${WF_WINDOW_DAYS:-45}"
WF_STEP_DAYS="${WF_STEP_DAYS:-15}"
WF_WORKERS="${WF_WORKERS:-1}"
WF_TIMEOUT_SEC="${WF_TIMEOUT_SEC:-900}"

echo "═══════════════════════════════════════════════"
echo "  TS132 WF-22 Validation — $TAG_BASE"
echo "  Symbols: $SYMBOLS | End: $END"
echo "═══════════════════════════════════════════════"
echo ""

"$PYTHON_BIN" scripts/run_generic_wf.py \
  --strategy triple_screen_v132 \
  --symbols "$SYMBOLS" \
  --tag "$TAG_BASE" \
  --end "$END" \
  --total_days "$WF_TOTAL_DAYS" \
  --window_days "$WF_WINDOW_DAYS" \
  --step_days "$WF_STEP_DAYS" \
  --workers "$WF_WORKERS" \
  --timeout_sec "$WF_TIMEOUT_SEC"
