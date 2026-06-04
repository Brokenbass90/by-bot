#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${1:-configs/crypto_income_static_v1_candidate.env}"
TAG="${CRYPTO_INCOME_TAG:-crypto_income_static_v1_candidate_$(date -u +%Y%m%d_%H%M%S)}"
END_DATE="${CRYPTO_INCOME_END:-2026-04-25}"
DAYS="${CRYPTO_INCOME_DAYS:-365}"
SYMBOLS="${CRYPTO_INCOME_SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT}"
STRATEGIES="${CRYPTO_INCOME_STRATEGIES:-alt_trendline_touch_v1,alt_resistance_fade_v1,alt_inplay_breakdown_v1,btc_eth_midterm_pullback}"
CACHE_DIR="${CRYPTO_INCOME_CACHE_DIR:-.cache/validated/crypto_static_v1_20260425}"
STRICT_EXACT_CACHE="${CRYPTO_INCOME_STRICT_EXACT_CACHE:-1}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found: $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-1}"
export BACKTEST_REQUIRE_EXACT_CACHE="${BACKTEST_REQUIRE_EXACT_CACHE:-$STRICT_EXACT_CACHE}"
if [[ "$STRICT_EXACT_CACHE" == "1" ]]; then
  export BACKTEST_CACHE_FALLBACK_ENABLE=0
else
  export BACKTEST_CACHE_FALLBACK_ENABLE="${BACKTEST_CACHE_FALLBACK_ENABLE:-1}"
fi

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

if [[ "$STRICT_EXACT_CACHE" == "1" ]]; then
  "$PYTHON_BIN" scripts/check_exact_kline_cache.py \
    --symbols "$SYMBOLS" \
    --interval 5 \
    --days "$DAYS" \
    --end-date "$END_DATE" \
    --cache-dir "$CACHE_DIR" \
    --strict
fi

"$PYTHON_BIN" backtest/run_portfolio.py \
  --symbols "$SYMBOLS" \
  --strategies "$STRATEGIES" \
  --days "$DAYS" \
  --end "$END_DATE" \
  --starting_equity 100 \
  --risk_pct "${CRYPTO_INCOME_RISK_PCT:-0.01}" \
  --leverage "${CRYPTO_INCOME_LEVERAGE:-1}" \
  --max_positions "${CRYPTO_INCOME_MAX_POSITIONS:-5}" \
  --fee_bps "${CRYPTO_INCOME_FEE_BPS:-6}" \
  --slippage_bps "${CRYPTO_INCOME_SLIPPAGE_BPS:-2}" \
  --cache "$CACHE_DIR" \
  --tag "$TAG"
