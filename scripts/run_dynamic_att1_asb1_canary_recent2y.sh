#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY_BIN="${PY_BIN:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY_BIN" ]; then
  PY_BIN="$(command -v python3)"
fi

export BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-0}"
export BACKTEST_CACHE_FALLBACK_ENABLE="${BACKTEST_CACHE_FALLBACK_ENABLE:-1}"

TAG="${TAG:-dynamic_core_att1_asb1_flat_range_recent2y}"
HEALTH_FILE="${HEALTH_FILE:-configs/strategy_health_att1_asb1_flat_range_canary.json}"
END_DATE="${END_DATE:-2026-04-21}"
TOTAL_DAYS="${TOTAL_DAYS:-730}"
WINDOW_DAYS="${WINDOW_DAYS:-30}"
STEP_DAYS="${STEP_DAYS:-30}"

exec "$PY_BIN" scripts/run_dynamic_crypto_annual.py \
  --end "$END_DATE" \
  --total_days "$TOTAL_DAYS" \
  --window_days "$WINDOW_DAYS" \
  --step_days "$STEP_DAYS" \
  --health "$HEALTH_FILE" \
  --tag "$TAG"
