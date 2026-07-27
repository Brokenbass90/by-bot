#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
LOG_DIR="${ROOT}/runtime/arb/logs"
INTERVAL_SECONDS="${CROSS_ARB_SHADOW_INTERVAL_SECONDS:-600}"

mkdir -p "${LOG_DIR}"

while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log="${LOG_DIR}/cross_exchange_funding_${stamp}.log"

  {
    echo "[$(date -u +%FT%TZ)] public scan"
    "${PYTHON}" "${ROOT}/scripts/cross_exchange_funding_scan.py" \
      --exchanges bybit,binance,bitget \
      --min-volume-usd 1000000 \
      --min-spread-apr-pct 5.5 \
      --top 30

    echo "[$(date -u +%FT%TZ)] executable validation"
    "${PYTHON}" "${ROOT}/scripts/cross_exchange_funding_validate.py" \
      --notional-usd 100 \
      --hold-hours 24 \
      --taker-fee-bps 6 \
      --max-slippage-bps 12 \
      --max-entry-basis-pct 1 \
      --min-spread-apr-pct 36 \
      --min-persistence-count 2 \
      --persistence-window-min 90 \
      --keep-failed

    echo "[$(date -u +%FT%TZ)] risk-zero paper lifecycle"
    "${PYTHON}" "${ROOT}/scripts/cross_exchange_funding_shadow.py" \
      --notional-usd 100 \
      --hold-hours 24 \
      --max-open 5 \
      --min-net-pct 0.20 \
      --min-persistence-count 3 \
      --taker-fee-bps 6 \
      --close-invalid-after-hours 2 \
      --close-invalid-count 3 \
      --reentry-cooldown-hours 6

    echo "[$(date -u +%FT%TZ)] bounded promotion gate"
    "${PYTHON}" "${ROOT}/scripts/arb_roi_calculator.py" \
      --state-json runtime/arb/cross_exchange_funding_shadow.json \
      --output-json runtime/arb/arb_roi_estimate.json \
      --capital 1000 \
      --min-closed-cycles 20 \
      --confirmation-closed-cycles 30 \
      --min-annualized-simple-pct 8 \
      --cohort explicit_validation_v1
  } >"${log}" 2>&1 || true

  ln -sfn "${log}" "${LOG_DIR}/latest.log"
  sleep "${INTERVAL_SECONDS}"
done
