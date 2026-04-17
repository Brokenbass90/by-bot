#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
ANNUAL="$ROOT/scripts/run_dynamic_crypto_annual.py"

END_DATE="${END_DATE:-2026-04-01}"
BASE_ENV_FILE="${BASE_ENV_FILE:-.env}"
WAIT_FOR_TAG="${WAIT_FOR_TAG:-current_crypto_livecore_20260417}"

wait_for_tag() {
  local tag="$1"
  while pgrep -f "$tag" >/dev/null 2>&1; do
    echo "[queue] waiting for $tag ..."
    sleep 30
  done
}

run_annual() {
  local tag="$1"
  shift
  echo "[queue] starting $tag"
  (
    cd "$ROOT"
    env "$@" "$PY" "$ANNUAL" \
      --end "$END_DATE" \
      --base-env-file "$BASE_ENV_FILE" \
      --tag "$tag" \
      --total_days 360 \
      --window_days 30 \
      --step_days 30 \
      --historical-hold-cycles 1
  )
  echo "[queue] finished $tag"
}

if [[ -n "${WAIT_FOR_TAG:-}" ]]; then
  wait_for_tag "$WAIT_FOR_TAG"
fi

run_annual \
  current_crypto_att1_only_20260417 \
  ENABLE_ATT1_TRADING=1 ATT1_RISK_MULT=0.70 \
  ENABLE_FLAT_TRADING=0 FLAT_RISK_MULT=0 \
  ENABLE_RANGE_TRADING=0 ARS1_RISK_MULT=0 \
  ENABLE_BREAKDOWN_TRADING=0 BREAKDOWN_RISK_MULT=0 \
  ENABLE_ASB1_TRADING=0 ASB1_RISK_MULT=0 \
  ENABLE_HZBO1_TRADING=0 HZBO1_RISK_MULT=0 \
  ENABLE_VWAP_TRADING=0 VWAP_RISK_MULT=0

run_annual \
  current_crypto_flat_only_20260417 \
  ENABLE_ATT1_TRADING=0 ATT1_RISK_MULT=0 \
  ENABLE_FLAT_TRADING=1 FLAT_RISK_MULT=1.00 \
  ENABLE_RANGE_TRADING=0 ARS1_RISK_MULT=0 \
  ENABLE_BREAKDOWN_TRADING=0 BREAKDOWN_RISK_MULT=0 \
  ENABLE_ASB1_TRADING=0 ASB1_RISK_MULT=0 \
  ENABLE_HZBO1_TRADING=0 HZBO1_RISK_MULT=0 \
  ENABLE_VWAP_TRADING=0 VWAP_RISK_MULT=0

run_annual \
  current_crypto_range_only_20260417 \
  ENABLE_ATT1_TRADING=0 ATT1_RISK_MULT=0 \
  ENABLE_FLAT_TRADING=0 FLAT_RISK_MULT=0 \
  ENABLE_RANGE_TRADING=1 ARS1_RISK_MULT=0.80 \
  ENABLE_BREAKDOWN_TRADING=0 BREAKDOWN_RISK_MULT=0 \
  ENABLE_ASB1_TRADING=0 ASB1_RISK_MULT=0 \
  ENABLE_HZBO1_TRADING=0 HZBO1_RISK_MULT=0 \
  ENABLE_VWAP_TRADING=0 VWAP_RISK_MULT=0

echo "[queue] all rehab annuals finished"
