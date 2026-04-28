#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY_BIN="${PY_BIN:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY_BIN" ]]; then
  PY_BIN="${PY_BIN_FALLBACK:-python3}"
fi

TAG="${CRYPTO_INCOME_DYNAMIC_TAG:-crypto_income_dynamic_v1_candidate_$(date -u +%Y%m%d_%H%M%S)}"
END_DATE="${CRYPTO_INCOME_DYNAMIC_END:-2026-04-25}"
TOTAL_DAYS="${CRYPTO_INCOME_DYNAMIC_DAYS:-360}"
WINDOW_DAYS="${CRYPTO_INCOME_DYNAMIC_WINDOW_DAYS:-30}"
STEP_DAYS="${CRYPTO_INCOME_DYNAMIC_STEP_DAYS:-30}"

export BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-1}"
export BACKTEST_CACHE_FALLBACK_ENABLE="${BACKTEST_CACHE_FALLBACK_ENABLE:-1}"

exec "$PY_BIN" scripts/run_dynamic_crypto_annual.py \
  --end "$END_DATE" \
  --total_days "$TOTAL_DAYS" \
  --window_days "$WINDOW_DAYS" \
  --step_days "$STEP_DAYS" \
  --base-env-file configs/crypto_income_static_v1_candidate.env \
  --registry "${CRYPTO_INCOME_DYNAMIC_REGISTRY:-configs/strategy_profile_registry.json}" \
  --policy configs/portfolio_allocator_policy_crypto_income_static_v1.json \
  --health configs/strategy_health_crypto_income_static_v1.json \
  --health-timeline configs/strategy_health_crypto_income_static_v1_empty_timeline.json \
  --cache-dir .cache/klines \
  --base_risk_pct "${CRYPTO_INCOME_DYNAMIC_RISK_PCT:-0.01}" \
  --leverage "${CRYPTO_INCOME_DYNAMIC_LEVERAGE:-1}" \
  --max_positions "${CRYPTO_INCOME_DYNAMIC_MAX_POSITIONS:-5}" \
  --fee_bps "${CRYPTO_INCOME_DYNAMIC_FEE_BPS:-6}" \
  --slippage_bps "${CRYPTO_INCOME_DYNAMIC_SLIPPAGE_BPS:-2}" \
  --historical-hold-cycles "${CRYPTO_INCOME_DYNAMIC_HOLD_CYCLES:-1}" \
  --tag "$TAG"
