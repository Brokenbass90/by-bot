#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY}"
STRATS="${FX_STRATEGIES:-trend_retest_session_v1,range_bounce_session_v1,breakout_continuation_session_v1,grid_reversion_session_v1,trend_pullback_rebound_v1}"
DATA_DIR="${FX_DATA_DIR:-data_cache/forex}"

echo "forex multi-strategy gate start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS}"
echo "strategies=${STRATS}"
echo "data_dir=${DATA_DIR}"

python3 scripts/run_forex_multi_strategy_gate.py \
  --pairs "${PAIRS}" \
  --strategies "${STRATS}" \
  --data-dir "${DATA_DIR}" \
  --session-start-utc "${FX_SESSION_START_UTC:-6}" \
  --session-end-utc "${FX_SESSION_END_UTC:-20}" \
  --max-bars "${FX_MAX_BARS:-0}" \
  --stress-spread-mult "${FX_STRESS_SPREAD_MULT:-1.5}" \
  --stress-swap-mult "${FX_STRESS_SWAP_MULT:-1.5}" \
  --recent-days "${FX_RECENT_DAYS:-28}" \
  --min-base-net "${FX_MIN_BASE_NET:-0}" \
  --min-stress-net "${FX_MIN_STRESS_NET:-0}" \
  --min-base-return-pct-est "${FX_MIN_BASE_RETURN_PCT_EST:--999}" \
  --min-stress-return-pct-est "${FX_MIN_STRESS_RETURN_PCT_EST:--999}" \
  --min-stress-return-pct-est-month "${FX_MIN_STRESS_RETURN_PCT_EST_MONTH:--999}" \
  --min-trades "${FX_MIN_TRADES:-40}" \
  --max-stress-dd "${FX_MAX_STRESS_DD:-300}" \
  --min-recent-stress-net "${FX_MIN_RECENT_STRESS_NET:-0}" \
  --min-recent-trades "${FX_MIN_RECENT_TRADES:-8}" \
  --top-n "${FX_TOP_N:-12}" \
  --tag "${FX_GATE_TAG:-fx_multi_gate}"

if [[ "${FX_UPDATE_STATE_AFTER_GATE:-1}" == "1" ]]; then
  TAG="${FX_GATE_TAG:-fx_multi_gate}"
  latest_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_${TAG}_* 2>/dev/null | head -n 1 || true)"
  if [[ -z "${latest_dir}" ]]; then
    latest_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_* 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -n "${latest_dir}" && -f "${latest_dir}/gated_summary.csv" ]]; then
    FX_GATED_CSV="${latest_dir}/gated_summary.csv" \
    FX_PASS_STREAK_TO_ACTIVE="${FX_PASS_STREAK_TO_ACTIVE:-2}" \
    FX_FAIL_STREAK_TO_BAN="${FX_FAIL_STREAK_TO_BAN:-2}" \
    FX_COOLDOWN_DAYS="${FX_COOLDOWN_DAYS:-7}" \
    FX_MAX_ACTIVE_COMBOS="${FX_MAX_ACTIVE_COMBOS:-3}" \
    bash scripts/run_forex_combo_state.sh
  else
    echo "warn: could not locate latest gated_summary.csv for state update"
  fi
fi
