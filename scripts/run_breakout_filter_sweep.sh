#!/usr/bin/env bash
set -euo pipefail

# Breakout filter sweep for live-like stack:
#   strategies: inplay_breakout + btc_eth_midterm_pullback
# Profiles:
#   strict / balanced / active / open
# For each profile:
#   base + stress costs, summary + monthly

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${END_DATE:-2026-03-01}"
DAYS="${DAYS:-360}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,AVAXUSDT}"
STRATEGIES="${STRATEGIES:-inplay_breakout,btc_eth_midterm_pullback}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.0}"

RUNSET_DIR="backtest_runs/breakout_filter_sweep_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"
SUMMARY="$RUNSET_DIR/summary.csv"

echo "profile,cost,tag,ending_equity,trades,net_pnl,pf,winrate,max_dd,run_dir" > "$SUMMARY"

echo "breakout filter sweep start: $(date -u '+%F %T UTC')" | tee "$REPORT"
echo "symbols=$SYMBOLS" | tee -a "$REPORT"
echo "strategies=$STRATEGIES" | tee -a "$REPORT"
echo "days=$DAYS end_date=$END_DATE" | tee -a "$REPORT"

run_case() {
  local profile="$1"
  local costs="$2"
  local fee="$3"
  local slip="$4"
  local q_enable="$5"
  local q_min="$6"
  local chase="$7"
  local late="$8"
  local pullback="$9"
  local impulse="${10}"
  local reclaim="${11}"
  local maxdist="${12}"
  local buffer="${13}"

  local tag="brfs_${profile}_${costs}_${DAYS}d"

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  BYBIT_DATA_POLITE_SLEEP_SEC="$POLITE_SLEEP" \
  BT_BREAKOUT_QUALITY_ENABLE="$q_enable" \
  BT_BREAKOUT_QUALITY_MIN_SCORE="$q_min" \
  BREAKOUT_MAX_CHASE_PCT="$chase" \
  BREAKOUT_MAX_LATE_VS_REF_PCT="$late" \
  BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT="$pullback" \
  BREAKOUT_IMPULSE_ATR_MULT="$impulse" \
  BREAKOUT_RECLAIM_ATR="$reclaim" \
  BREAKOUT_MAX_DIST_ATR="$maxdist" \
  BREAKOUT_BUFFER_ATR="$buffer" \
  python3 backtest/run_portfolio.py \
    --symbols "$SYMBOLS" \
    --strategies "$STRATEGIES" \
    --days "$DAYS" --end "$END_DATE" \
    --tag "$tag" \
    --starting_equity "$STARTING_EQUITY" \
    --risk_pct "$RISK_PCT" \
    --leverage "$LEVERAGE" \
    --max_positions "$MAX_POSITIONS" \
    --fee_bps "$fee" \
    --slippage_bps "$slip" | tee -a "$REPORT"

  local run_dir
  run_dir="$(ls -1dt backtest_runs/*"${tag}" | head -n 1)"
  echo "run_dir=$run_dir" | tee -a "$REPORT"
  cat "$run_dir/summary.csv" | tee -a "$REPORT"
  python3 scripts/monthly_pnl.py "$run_dir/trades.csv" | tee -a "$REPORT"

  local row
  row="$(tail -n 1 "$run_dir/summary.csv")"
  local ending trades net pf win maxdd
  ending="$(echo "$row" | cut -d, -f7)"
  trades="$(echo "$row" | cut -d, -f8)"
  net="$(echo "$row" | cut -d, -f9)"
  pf="$(echo "$row" | cut -d, -f10)"
  win="$(echo "$row" | cut -d, -f11)"
  maxdd="$(echo "$row" | cut -d, -f14)"
  echo "${profile},${costs},${tag},${ending},${trades},${net},${pf},${win},${maxdd},${run_dir}" >> "$SUMMARY"
}

# strict (close to current live quality gate)
run_case strict base   6  2  1 0.58 0.15 0.35 0.08 1.00 0.15 1.20 0.10
run_case strict stress 10 10 1 0.58 0.15 0.35 0.08 1.00 0.15 1.20 0.10

# balanced (slightly looser)
run_case balanced base   6  2  1 0.55 0.18 0.45 0.05 0.90 0.12 1.35 0.08
run_case balanced stress 10 10 1 0.55 0.18 0.45 0.05 0.90 0.12 1.35 0.08

# active (noticeably looser)
run_case active base   6  2  1 0.52 0.22 0.55 0.03 0.80 0.10 1.50 0.06
run_case active stress 10 10 1 0.52 0.22 0.55 0.03 0.80 0.10 1.50 0.06

# open (quality gate disabled, exploration profile)
run_case open base   6  2  0 0.00 0.25 0.70 0.00 0.75 0.08 1.70 0.05
run_case open stress 10 10 0 0.00 0.25 0.70 0.00 0.75 0.08 1.70 0.05

echo "" | tee -a "$REPORT"
echo "=== SUMMARY (stress net desc) ===" | tee -a "$REPORT"
SUMMARY_PATH="$SUMMARY" python3 - <<'PY' | tee -a "$REPORT"
import csv
import os
from pathlib import Path
p=Path(os.environ["SUMMARY_PATH"])
rows=[]
with p.open(newline='',encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        if row.get('cost')=='stress':
            try:row['_net']=float(row.get('net_pnl') or 0)
            except: row['_net']=0.0
            rows.append(row)
rows.sort(key=lambda x:x['_net'], reverse=True)
for x in rows:
    print(f"{x['profile']:>8} stress net={x['net_pnl']} pf={x['pf']} trades={x['trades']} dd={x['max_dd']}")
PY

echo "" | tee -a "$REPORT"
echo "breakout filter sweep done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "summary=$SUMMARY" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"
