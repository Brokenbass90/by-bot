#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="logs/midterm_after_fx_20260705"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_${STAMP}.log"

{
  echo "[after-fx-midterm] start_utc=$(date -u +%FT%TZ)"
  echo "[after-fx-midterm] waiting for screen fx_after_att1_20260705"
  while (screen -ls 2>/dev/null || true) | grep -q "fx_after_att1_20260705"; do
    sleep 60
  done

  echo "[after-fx-midterm] FX finished; launching midterm short_v2 refreshed window"
  TAG_BASE=midterm_short_v2_refresh_20260705 \
  END=2026-07-04 \
  DAYS=1095 \
  WF_TOTAL_DAYS=360 \
  WF_WINDOW_DAYS=45 \
  WF_STEP_DAYS=15 \
  WF_WORKERS=1 \
  BACKTEST_CACHE_ONLY=0 \
  CACHE_ONLY=0 \
  bash scripts/run_midterm_short_v2_backtests.sh

  echo "[after-fx-midterm] launching midterm v3 refreshed window, tests 1-2 only"
  TAG=midterm_v3_refresh_20260705 \
  END=2026-07-04 \
  DAYS=1095 \
  RUN_V1_COMPARE=0 \
  RUN_BEAR_STACK=0 \
  BACKTEST_CACHE_ONLY=0 \
  CACHE_ONLY=0 \
  bash scripts/run_midterm_v3_backtest.sh

  echo "[after-fx-midterm] done_utc=$(date -u +%FT%TZ)"
} 2>&1 | tee "$LOG_FILE"
