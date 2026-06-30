#!/usr/bin/env bash
# Local-only overnight research runner.
#
# Purpose: collect OOS evidence without stressing the 1GB live VPS.
# Safe defaults:
# - BACKTEST_CACHE_ONLY=1: no network dependency.
# - sequential runs: no parallel memory spike.
# - no live config writes, no broker/API calls.
#
# If the Mac sleeps, this stops. Live server is unaffected.
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

PY="${PY:-.venv/bin/python}"
TS="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="logs/manual_research"
LOG="$LOG_DIR/local_overnight_20260630_${TS}.log"
mkdir -p "$LOG_DIR" reports

echo "LOCAL_OVERNIGHT_START $(date -u)" | tee "$LOG"
echo "root=$ROOT_DIR" | tee -a "$LOG"

run() {
  echo "" | tee -a "$LOG"
  echo ">>> $*" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  echo "<<< rc=$rc" | tee -a "$LOG"
  return "$rc"
}

run "$PY" -m pytest \
  tests/test_range_filter.py \
  tests/test_pump_exhaustion.py \
  tests/test_retest_quality.py \
  tests/test_elder_filter.py \
  tests/test_breakout_confirm.py \
  tests/test_market_context.py \
  tests/test_adaptive_context.py \
  tests/test_inplay_retest_v4.py \
  tests/test_backtest_next_open.py \
  tests/test_strategy_catalog.py

run "$PY" scripts/market_survey.py \
  --tf 60 \
  --bars 300 \
  --out "reports/market_survey_overnight_20260630.csv"

# InPlay V4: short-only retest/fade grid. This is a research screen, not live.
for universe in "ADAUSDT,DOGEUSDT,SUIUSDT" "LINKUSDT,SOLUSDT,ADAUSDT"; do
  u_tag="$(echo "$universe" | tr ',' '_' | tr '[:upper:]' '[:lower:]')"
  for rr in 2.0 2.5 3.0; do
    for adaptive in 0 1; do
      tag="irv4_local_oos_${u_tag}_rr${rr}_ad${adaptive}_20260630"
      echo "" | tee -a "$LOG"
      echo ">>> IRV4 $tag" | tee -a "$LOG"
      IRV4_ALLOW_LONG=0 \
      IRV4_ALLOW_SHORT=1 \
      IRV4_TP_RR="$rr" \
      IRV4_ADAPTIVE="$adaptive" \
      BACKTEST_CACHE_ONLY=1 \
      "$PY" backtest/run_portfolio.py \
        --symbols "$universe" \
        --strategies inplay_retest_v4 \
        --days 240 \
        --end 2026-06-30 \
        --tag "$tag" \
        --starting_equity 100 \
        --risk_pct 0.005 \
        --leverage 1 \
        --max_positions 2 \
        --fee_bps 6 \
        --slippage_bps 2 \
        --entry-on-next-open 2>&1 | tee -a "$LOG"
      echo "<<< IRV4 rc=${PIPESTATUS[0]}" | tee -a "$LOG"
    done
  done
done

# SpikeFadeV3: re-check the cleanest known diversifier slice (LINK short-only).
for days in 90 240 360; do
  tag="spike_fade_v3_link_short_oos_${days}d_20260630"
  echo "" | tee -a "$LOG"
  echo ">>> SFV3 $tag" | tee -a "$LOG"
  SFV3_ALLOW_LONG=0 \
  SFV3_ALLOW_SHORT=1 \
  SFV3_ALLOW=LINKUSDT \
  SFV3_LEVEL_TOL_ATR=0.35 \
  SFV3_SPIKE_MIN_PCT=4.0 \
  SFV3_TAG_LEVEL_ATR=0.8 \
  SFV3_REJECT_FRAC=0.55 \
  SFV3_STOP_BUFFER_ATR=0.4 \
  BACKTEST_CACHE_ONLY=1 \
  "$PY" backtest/run_portfolio.py \
    --symbols LINKUSDT \
    --strategies spike_fade_v3 \
    --days "$days" \
    --end 2026-06-30 \
    --tag "$tag" \
    --starting_equity 100 \
    --risk_pct 0.005 \
    --leverage 1 \
    --max_positions 1 \
    --fee_bps 6 \
    --slippage_bps 2 \
    --entry-on-next-open 2>&1 | tee -a "$LOG"
  echo "<<< SFV3 rc=${PIPESTATUS[0]}" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo ">>> SUMMARY" | tee -a "$LOG"
"$PY" - <<'PY' 2>&1 | tee -a "$LOG"
import csv
import glob
import os

tags = ("irv4_local_oos_", "spike_fade_v3_link_short_oos_")
paths = []
for p in glob.glob("backtest_runs/portfolio_*/summary.csv"):
    try:
        with open(p, newline="") as f:
            rows = list(csv.DictReader(f))
        if rows and any(rows[0].get("tag", "").startswith(t) for t in tags):
            paths.append((os.path.getmtime(p), p, rows[0]))
    except Exception:
        pass
for _, p, r in sorted(paths)[-40:]:
    print(
        f"{r.get('tag')} trades={r.get('trades')} net={r.get('net_pnl')} "
        f"pf={r.get('profit_factor')} wr={r.get('winrate')} dd={r.get('max_drawdown')} "
        f"file={p}"
    )
PY

echo "LOCAL_OVERNIGHT_DONE $(date -u)" | tee -a "$LOG"
echo "log=$LOG"
