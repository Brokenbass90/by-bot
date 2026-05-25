#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs runtime/equities_yf_cache

stamp="$(date -u +%Y%m%d_%H%M%S)"
log="logs/alpaca_v39_robustness_validation_${stamp}.log"

if [[ "${1:-}" == "--wait-for-crypto-research" ]]; then
  echo "[alpaca-v39-validation] queued behind ATT1 research at ${stamp} UTC" | tee -a "$log"
  while pgrep -fal 'run_strategy_autoresearch.py --spec configs/autoresearch/(att1_density_v3_more_pivots_v1|att1_short_slope_v1).json' >/dev/null; do
    sleep 60
  done
fi

run_case() {
  local tag="$1"
  local start="$2"
  local end="$3"

  PYTHONDONTWRITEBYTECODE=1 python3 scripts/alpaca_v3_event_backtest.py \
    --start "$start" \
    --end "$end" \
    --capital 1000 \
    --max-positions 4 \
    --profit-trigger-pct 8 \
    --profit-pullback-pct 2.5 \
    --stop-pct 9 \
    --peer-outperform-pct 15 \
    --max-age-days 30 \
    --hard-max-age-days 60 \
    --fee-bps 10 \
    --tag "${tag}_${stamp}" \
    --cache-dir runtime/equities_yf_cache 2>&1 | tee -a "$log"
}

echo "[alpaca-v39-validation] started ${stamp} UTC" | tee -a "$log"
run_case "fee_stress_24m" "2024-05-01" "2026-05-01"
run_case "oos_12m_fee_stress" "2025-05-01" "2026-05-01"
run_case "bear_2022_fee_stress" "2022-01-01" "2023-01-01"
echo "[alpaca-v39-validation] finished $(date -u +%Y%m%d_%H%M%S) UTC" | tee -a "$log"
