#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY}"
STRATS="${FX_STRATEGIES:-trend_retest_session_v1:conservative,trend_retest_session_v1:active,trend_retest_session_v1:eurusd_canary,range_bounce_session_v1:default,range_bounce_session_v1:loose,breakout_continuation_session_v1:default,breakout_continuation_session_v1:strict,breakout_continuation_session_v1:active,grid_reversion_session_v1:default,grid_reversion_session_v1:strict,grid_reversion_session_v1:active,grid_reversion_session_v1:eurjpy_canary,trend_pullback_rebound_v1:default,trend_pullback_rebound_v1:strict}"

FAST_TAG="${FX_FAST_TAG:-fx_stage_fast}"
FULL_TAG="${FX_FULL_TAG:-fx_stage_full}"

echo "forex two-stage gate start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS}"
echo "strategies=${STRATS}"

echo ""
echo ">>> STAGE 1: FAST SCOUT"
FX_UPDATE_STATE_AFTER_GATE=0 \
FX_GATE_TAG="${FAST_TAG}" \
FX_PAIRS="${PAIRS}" \
FX_STRATEGIES="${STRATS}" \
FX_MAX_BARS="${FX_FAST_MAX_BARS:-4500}" \
FX_MIN_TRADES="${FX_FAST_MIN_TRADES:-15}" \
FX_TOP_N="${FX_FAST_TOP_N:-20}" \
FX_MIN_BASE_NET="${FX_FAST_MIN_BASE_NET:-0}" \
FX_MIN_STRESS_NET="${FX_FAST_MIN_STRESS_NET:-0}" \
FX_MAX_STRESS_DD="${FX_FAST_MAX_STRESS_DD:-300}" \
FX_MIN_RECENT_STRESS_NET="${FX_FAST_MIN_RECENT_STRESS_NET:-0}" \
FX_MIN_RECENT_TRADES="${FX_FAST_MIN_RECENT_TRADES:-8}" \
bash scripts/run_forex_multi_strategy_gate.sh

fast_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_${FAST_TAG}_* 2>/dev/null | head -n 1 || true)"
if [[ -z "${fast_dir}" || ! -f "${fast_dir}/selected_combos.csv" ]]; then
  echo "fast stage output not found"
  exit 1
fi

active_csv="docs/forex_combo_active_latest.csv"
if [[ ! -f "${active_csv}" ]]; then
  active_csv=""
fi

extracted="$(python3 - <<'PY' "${fast_dir}/selected_combos.csv" "${FX_FULL_COMBO_LIMIT:-10}" "${active_csv}" "${FX_INCLUDE_ACTIVE_IN_FULL:-1}"
import csv,sys
csv_path=sys.argv[1]
limit=max(1,int(sys.argv[2]))
active_csv=sys.argv[3]
include_active=str(sys.argv[4]).strip() not in ("0","false","False","no","No")
pairs=[]
strats=[]
with open(csv_path,newline='',encoding='utf-8') as f:
    for i,row in enumerate(csv.DictReader(f)):
        if i>=limit:
            break
        p=row.get('pair','').strip().upper()
        s=row.get('strategy','').strip()
        if p and p not in pairs:
            pairs.append(p)
        if s and s not in strats:
            strats.append(s)
if include_active and active_csv:
    with open(active_csv,newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            p=row.get('pair','').strip().upper()
            s=row.get('strategy','').strip()
            if p and p not in pairs:
                pairs.append(p)
            if s and s not in strats:
                strats.append(s)
print(",".join(pairs))
print(",".join(strats))
PY
)"

full_pairs="$(printf '%s\n' "${extracted}" | sed -n '1p')"
full_strats="$(printf '%s\n' "${extracted}" | sed -n '2p')"
if [[ -z "${full_pairs}" || -z "${full_strats}" ]]; then
  echo "no fast candidates found for full confirm"
  exit 1
fi

echo ""
echo ">>> STAGE 2: FULL CONFIRM"
echo "full_pairs=${full_pairs}"
echo "full_strategies=${full_strats}"

FX_UPDATE_STATE_AFTER_GATE=0 \
FX_GATE_TAG="${FULL_TAG}" \
FX_PAIRS="${full_pairs}" \
FX_STRATEGIES="${full_strats}" \
FX_MAX_BARS=0 \
FX_MIN_TRADES="${FX_FULL_MIN_TRADES:-20}" \
FX_TOP_N="${FX_FULL_TOP_N:-12}" \
FX_MIN_BASE_NET="${FX_FULL_MIN_BASE_NET:-0}" \
FX_MIN_STRESS_NET="${FX_FULL_MIN_STRESS_NET:-0}" \
FX_MAX_STRESS_DD="${FX_FULL_MAX_STRESS_DD:-300}" \
FX_MIN_RECENT_STRESS_NET="${FX_FULL_MIN_RECENT_STRESS_NET:-0}" \
FX_MIN_RECENT_TRADES="${FX_FULL_MIN_RECENT_TRADES:-8}" \
bash scripts/run_forex_multi_strategy_gate.sh

full_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_${FULL_TAG}_* 2>/dev/null | head -n 1 || true)"
if [[ -z "${full_dir}" || ! -f "${full_dir}/gated_summary.csv" ]]; then
  echo "full stage output not found"
  exit 1
fi

echo ""
echo ">>> STAGE 3: STATE UPDATE"
FX_GATED_CSV="${full_dir}/gated_summary.csv" \
FX_PASS_STREAK_TO_ACTIVE="${FX_PASS_STREAK_TO_ACTIVE:-2}" \
FX_FAIL_STREAK_TO_BAN="${FX_FAIL_STREAK_TO_BAN:-2}" \
FX_COOLDOWN_DAYS="${FX_COOLDOWN_DAYS:-7}" \
FX_MAX_ACTIVE_COMBOS="${FX_MAX_ACTIVE_COMBOS:-3}" \
bash scripts/run_forex_combo_state.sh

echo ""
echo "two-stage gate done"
echo "fast_dir=${fast_dir}"
echo "full_dir=${full_dir}"
