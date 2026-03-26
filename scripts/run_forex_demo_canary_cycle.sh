#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,EURJPY,USDJPY,AUDJPY,USDCAD,GBPJPY}"

echo "forex demo canary cycle start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS}"
echo "profile=demo_canary"
echo "full_max_bars=${FX_FULL_MAX_BARS:-30000} min_trades=${FX_FULL_MIN_TRADES:-40} max_dd=${FX_FULL_MAX_STRESS_DD:-350}"
echo "recent_stress_min=${FX_FULL_MIN_RECENT_STRESS_NET:--150} stress_ret_min=${FX_FULL_MIN_STRESS_RETURN_PCT_EST:-0} pass_streak_to_active=${FX_PASS_STREAK_TO_ACTIVE:-1}"

FX_PAIRS="${PAIRS}" \
FX_GATE_TAG="${FX_GATE_TAG:-fx_demo_canary}" \
FX_FULL_MAX_BARS="${FX_FULL_MAX_BARS:-30000}" \
FX_FULL_MIN_TRADES="${FX_FULL_MIN_TRADES:-40}" \
FX_FULL_MIN_BASE_NET="${FX_FULL_MIN_BASE_NET:-0}" \
FX_FULL_MIN_STRESS_NET="${FX_FULL_MIN_STRESS_NET:-0}" \
FX_FULL_MIN_STRESS_RETURN_PCT_EST="${FX_FULL_MIN_STRESS_RETURN_PCT_EST:-0}" \
FX_FULL_MAX_STRESS_DD="${FX_FULL_MAX_STRESS_DD:-350}" \
FX_FULL_MIN_RECENT_STRESS_NET="${FX_FULL_MIN_RECENT_STRESS_NET:--150}" \
FX_FULL_MIN_RECENT_TRADES="${FX_FULL_MIN_RECENT_TRADES:-8}" \
FX_FULL_TOP_N="${FX_FULL_TOP_N:-10}" \
FX_PASS_STREAK_TO_ACTIVE="${FX_PASS_STREAK_TO_ACTIVE:-1}" \
FX_FAIL_STREAK_TO_BAN="${FX_FAIL_STREAK_TO_BAN:-3}" \
FX_MAX_ACTIVE_COMBOS="${FX_MAX_ACTIVE_COMBOS:-3}" \
FX_MAX_ACTIVE_PER_PAIR="${FX_MAX_ACTIVE_PER_PAIR:-1}" \
FX_CANARY_RISK_MULT="${FX_CANARY_RISK_MULT:-0.50}" \
bash scripts/run_forex_two_stage_gate.sh

if [[ "${FX_EXPORT_DEMO_ENV_AFTER_CYCLE:-1}" == "1" ]]; then
  bash scripts/export_forex_demo_env.sh
fi

echo ""
echo "demo canary cycle done"
echo "active: docs/forex_combo_active_latest.txt"
echo "canary: docs/forex_live_canary_combos_latest.txt"
echo "env: docs/forex_live_filter_latest.env"
