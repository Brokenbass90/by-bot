#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

GATED_CSV="${FX_GATED_CSV:-}"
if [[ -z "${GATED_CSV}" ]]; then
  latest_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_* 2>/dev/null | head -n 1 || true)"
  if [[ -z "${latest_dir}" ]]; then
    echo "No forex_multi_strategy_gate outputs found under backtest_runs/"
    exit 1
  fi
  GATED_CSV="${latest_dir}/gated_summary.csv"
fi

if [[ ! -f "${GATED_CSV}" ]]; then
  echo "gated csv not found: ${GATED_CSV}"
  exit 1
fi

echo "forex combo state start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "gated_csv=${GATED_CSV}"

python3 scripts/update_forex_combo_state.py \
  --gated-csv "${GATED_CSV}" \
  --state-csv "${FX_STATE_CSV:-docs/forex_combo_state_latest.csv}" \
  --actions-csv "${FX_ACTIONS_CSV:-docs/forex_combo_actions_latest.csv}" \
  --active-csv "${FX_ACTIVE_CSV:-docs/forex_combo_active_latest.csv}" \
  --active-txt "${FX_ACTIVE_TXT:-docs/forex_combo_active_latest.txt}" \
  --pass-streak-to-active "${FX_PASS_STREAK_TO_ACTIVE:-2}" \
  --fail-streak-to-ban "${FX_FAIL_STREAK_TO_BAN:-2}" \
  --cooldown-days "${FX_COOLDOWN_DAYS:-7}" \
  --max-active "${FX_MAX_ACTIVE_COMBOS:-3}" \
  --max-active-per-pair "${FX_MAX_ACTIVE_PER_PAIR:-1}" \
  --soft-canary-enabled "${FX_SOFT_CANARY_ENABLED:-1}" \
  --soft-canary-base-min "${FX_SOFT_CANARY_BASE_MIN:-0}" \
  --soft-canary-stress-min "${FX_SOFT_CANARY_STRESS_MIN:-25}" \
  --soft-canary-recent-min "${FX_SOFT_CANARY_RECENT_MIN:--2}" \
  --soft-canary-min-trades "${FX_SOFT_CANARY_MIN_TRADES:-40}" \
  --soft-canary-max-dd "${FX_SOFT_CANARY_MAX_DD:-250}" \
  --demote-unseen "${FX_DEMOTE_UNSEEN:-1}"

if [[ "${FX_EXPORT_LIVE_FILTERS_AFTER_STATE:-1}" == "1" ]]; then
  python3 scripts/export_forex_live_filters.py \
    --state-csv "${FX_STATE_CSV:-docs/forex_combo_state_latest.csv}" \
    --out-dir "${FX_LIVE_FILTER_OUT_DIR:-docs}" \
    --prefix "${FX_LIVE_FILTER_PREFIX:-forex_live_filter_latest}" \
    --canary-risk-mult "${FX_CANARY_RISK_MULT:-0.50}"
fi

echo ""
echo "state file: ${FX_STATE_CSV:-docs/forex_combo_state_latest.csv}"
echo "active combos: ${FX_ACTIVE_TXT:-docs/forex_combo_active_latest.txt}"
