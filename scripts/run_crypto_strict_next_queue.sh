#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

mkdir -p logs

IVB1_LIMIT="${IVB1_LIMIT:-12}"
PFS1_LIMIT="${PFS1_LIMIT:-12}"
JOBS="${JOBS:-2}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT}"
FUNDING_DIR="${FUNDING_DIR:-data/funding_rates/crypto_static_v1_20260425}"

"$PYTHON_BIN" scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/package_ivb1_impulse_additive_v2_riskfix.json \
  --limit "$IVB1_LIMIT" \
  --jobs "$JOBS" \
  > logs/ivb1_strict_riskfix_20260604.log 2>&1

"$PYTHON_BIN" scripts/funding_rate_fetcher.py \
  --history-all \
  --symbols "$SYMBOLS" \
  --days 365 \
  --end-date 2026-04-25 \
  --out-dir "$FUNDING_DIR" \
  > logs/pfs1_funding_history_20260604.log 2>&1

"$PYTHON_BIN" scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/package_pfs1_pump_fade_v1.json \
  --limit "$PFS1_LIMIT" \
  --jobs "$JOBS" \
  > logs/pfs1_strict_funding_20260604.log 2>&1
