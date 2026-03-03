#!/usr/bin/env bash
set -euo pipefail

# Sweep only BREAKOUT_IMPULSE_ATR_MULT around current live profile.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${END_DATE:-2026-03-01}"
DAYS="${DAYS:-180}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,AVAXUSDT}"
STRATEGIES="${STRATEGIES:-inplay_breakout,btc_eth_midterm_pullback}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.0}"
IMPULSES_CSV="${IMPULSES_CSV:-0.80,0.75,0.70,0.65}"

# Hold all other live-ish breakout params fixed
Q_ENABLE="${Q_ENABLE:-1}"
Q_MIN="${Q_MIN:-0.52}"
CHASE="${CHASE:-0.22}"
LATE="${LATE:-0.55}"
PULLBACK="${PULLBACK:-0.03}"
RECLAIM="${RECLAIM:-0.10}"
MAXDIST="${MAXDIST:-1.50}"
BUFFER="${BUFFER:-0.06}"

RUNSET_DIR="backtest_runs/breakout_impulse_sweep_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"
SUMMARY="$RUNSET_DIR/summary.csv"

echo "impulse,cost,tag,ending_equity,trades,net_pnl,pf,winrate,max_dd,run_dir" > "$SUMMARY"

echo "breakout impulse sweep start: $(date -u '+%F %T UTC')" | tee "$REPORT"
echo "symbols=$SYMBOLS" | tee -a "$REPORT"
echo "strategies=$STRATEGIES" | tee -a "$REPORT"
echo "days=$DAYS end_date=$END_DATE" | tee -a "$REPORT"
echo "impulses=$IMPULSES_CSV" | tee -a "$REPORT"
echo "fixed: q_min=$Q_MIN chase=$CHASE late=$LATE pullback=$PULLBACK reclaim=$RECLAIM maxdist=$MAXDIST buffer=$BUFFER" | tee -a "$REPORT"

run_case() {
  local impulse="$1"
  local costs="$2"
  local fee="$3"
  local slip="$4"
  local tag="bris_i${impulse//./}_${costs}_${DAYS}d"

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  BYBIT_DATA_POLITE_SLEEP_SEC="$POLITE_SLEEP" \
  BT_BREAKOUT_QUALITY_ENABLE="$Q_ENABLE" \
  BT_BREAKOUT_QUALITY_MIN_SCORE="$Q_MIN" \
  BREAKOUT_MAX_CHASE_PCT="$CHASE" \
  BREAKOUT_MAX_LATE_VS_REF_PCT="$LATE" \
  BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT="$PULLBACK" \
  BREAKOUT_IMPULSE_ATR_MULT="$impulse" \
  BREAKOUT_RECLAIM_ATR="$RECLAIM" \
  BREAKOUT_MAX_DIST_ATR="$MAXDIST" \
  BREAKOUT_BUFFER_ATR="$BUFFER" \
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

  local row
  row="$(tail -n 1 "$run_dir/summary.csv")"
  local ending trades net pf win maxdd
  ending="$(echo "$row" | cut -d, -f7)"
  trades="$(echo "$row" | cut -d, -f8)"
  net="$(echo "$row" | cut -d, -f9)"
  pf="$(echo "$row" | cut -d, -f10)"
  win="$(echo "$row" | cut -d, -f11)"
  maxdd="$(echo "$row" | cut -d, -f14)"
  echo "${impulse},${costs},${tag},${ending},${trades},${net},${pf},${win},${maxdd},${run_dir}" >> "$SUMMARY"
}

IFS=',' read -r -a IMPULSES <<< "$IMPULSES_CSV"
for x in "${IMPULSES[@]}"; do
  impulse="$(echo "$x" | xargs)"
  [[ -z "$impulse" ]] && continue
  run_case "$impulse" base 6 2
  run_case "$impulse" stress 10 10
done

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
            try: row['_net']=float(row.get('net_pnl') or 0)
            except: row['_net']=0.0
            rows.append(row)
rows.sort(key=lambda x:x['_net'], reverse=True)
for x in rows:
    print(f"impulse={x['impulse']} stress net={x['net_pnl']} pf={x['pf']} trades={x['trades']} dd={x['max_dd']}")
PY

echo "" | tee -a "$REPORT"
echo "breakout impulse sweep done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "summary=$SUMMARY" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"
