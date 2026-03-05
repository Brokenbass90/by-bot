#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

RAW_CSV="${EQ_WF_RAW_CSV:-}"
if [[ -z "${RAW_CSV}" ]]; then
  latest_dir="$(ls -1dt backtest_runs/equities_wf_gate_* 2>/dev/null | head -n 1 || true)"
  if [[ -z "${latest_dir}" ]]; then
    echo "No equities_wf_gate outputs found under backtest_runs/"
    exit 1
  fi
  RAW_CSV="${latest_dir}/raw_walkforward.csv"
fi

if [[ ! -f "${RAW_CSV}" ]]; then
  echo "raw csv not found: ${RAW_CSV}"
  exit 1
fi

echo "equities combo state start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "raw_csv=${RAW_CSV}"

python3 scripts/update_equities_combo_state.py \
  --raw-csv "${RAW_CSV}" \
  --state-csv "${EQ_STATE_CSV:-docs/equities_combo_state_latest.csv}" \
  --actions-csv "${EQ_ACTIONS_CSV:-docs/equities_combo_actions_latest.csv}" \
  --active-csv "${EQ_ACTIVE_CSV:-docs/equities_combo_active_latest.csv}" \
  --active-txt "${EQ_ACTIVE_TXT:-docs/equities_combo_active_latest.txt}" \
  --active-tickers-txt "${EQ_ACTIVE_TICKERS_TXT:-docs/equities_active_tickers_latest.txt}" \
  --pass-streak-to-active "${EQ_PASS_STREAK_TO_ACTIVE:-2}" \
  --fail-streak-to-ban "${EQ_FAIL_STREAK_TO_BAN:-2}" \
  --cooldown-days "${EQ_COOLDOWN_DAYS:-7}" \
  --max-active "${EQ_MAX_ACTIVE_COMBOS:-6}" \
  --min-segments "${EQ_WF_MIN_SEGMENTS:-4}" \
  --min-both-positive-pct "${EQ_WF_MIN_BOTH_POS_PCT:-55}" \
  --min-stress-total-cents "${EQ_WF_MIN_STRESS_TOTAL:-0}" \
  --soft-canary-enabled "${EQ_SOFT_CANARY_ENABLED:-1}" \
  --soft-canary-min-both-pct "${EQ_SOFT_CANARY_MIN_BOTH_PCT:-50}" \
  --soft-canary-min-stress-cents "${EQ_SOFT_CANARY_MIN_STRESS_CENTS:-100}" \
  --soft-canary-min-trades "${EQ_SOFT_CANARY_MIN_TRADES:-20}" \
  --demote-unseen "${EQ_DEMOTE_UNSEEN:-1}"

echo ""
echo "state file: ${EQ_STATE_CSV:-docs/equities_combo_state_latest.csv}"
echo "active combos: ${EQ_ACTIVE_TXT:-docs/equities_combo_active_latest.txt}"
echo "active tickers: ${EQ_ACTIVE_TICKERS_TXT:-docs/equities_active_tickers_latest.txt}"
