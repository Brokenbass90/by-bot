#!/usr/bin/env bash
set -euo pipefail

# Run baseline backtests for each strategy on the SAME symbol universe,
# extracted from a portfolio summary.csv.
#
# Usage:
#   bash scripts/run_baselines_30d.sh backtest_runs/portfolio_*/summary.csv [END_YYYY_MM_DD] [DAYS]

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/run_baselines_30d.sh <portfolio_summary_csv> [END_YYYY_MM_DD] [DAYS]" >&2
  exit 2
fi

TARGET="$1"
if [[ -d "$TARGET" ]]; then
  SUMMARY="$TARGET/summary.csv"
else
  SUMMARY="$TARGET"
fi

if [[ ! -f "$SUMMARY" ]]; then
  echo "File not found: $SUMMARY" >&2
  echo "Available portfolio runs:" >&2
  ls -1dt backtest_runs/portfolio_* 2>/dev/null | head -n 10 >&2 || true
  exit 2
fi
END_DATE="${2:-2026-02-01}"
DAYS="${3:-30}"

SYMBOLS="$(python3 scripts/symbols_from_summary.py "$SUMMARY")"
echo "Symbols: $SYMBOLS"
echo "End: $END_DATE  Days: $DAYS"

python3 backtest/run_month.py --symbols "$SYMBOLS" --days "$DAYS" --end "$END_DATE" --strategies bounce --tag bounce_${DAYS}d_baseline
python3 backtest/run_month.py --symbols "$SYMBOLS" --days "$DAYS" --end "$END_DATE" --strategies range --tag range_${DAYS}d_baseline
python3 backtest/run_month.py --symbols "$SYMBOLS" --days "$DAYS" --end "$END_DATE" --strategies pump_fade --tag pumpfade_${DAYS}d_baseline

INPLAY_EXIT_MODE="${INPLAY_EXIT_MODE:-runner}" \
INPLAY_PARTIAL_RS="${INPLAY_PARTIAL_RS:-1,2,4}" \
INPLAY_PARTIAL_FRACS="${INPLAY_PARTIAL_FRACS:-0.50,0.25,0.15}" \
INPLAY_TRAIL_ATR_MULT="${INPLAY_TRAIL_ATR_MULT:-2.5}" \
INPLAY_TRAIL_ATR_PERIOD="${INPLAY_TRAIL_ATR_PERIOD:-14}" \
INPLAY_TIME_STOP_BARS="${INPLAY_TIME_STOP_BARS:-288}" \
INPLAY_USE_LEVEL_TP="${INPLAY_USE_LEVEL_TP:-1}" \
INPLAY_LEVEL_LOOKBACK_1H="${INPLAY_LEVEL_LOOKBACK_1H:-72}" \
INPLAY_LEVEL_MARGIN_PCT="${INPLAY_LEVEL_MARGIN_PCT:-0.003}" \
python3 backtest/run_month.py --symbols "$SYMBOLS" --days "$DAYS" --end "$END_DATE" --strategies inplay --tag inplay_runner_${DAYS}d_baseline
