#!/usr/bin/env bash
set -euo pipefail

# Quick candidate scan (base/stress) for next non-live strategies.
# Produces ranking by stress net/PF.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${END_DATE:-2026-03-01}"
DAYS="${DAYS:-180}"
SYMBOLS_ALL="${SYMBOLS_ALL:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,AVAXUSDT}"
SYMBOLS_BTCETH="${SYMBOLS_BTCETH:-BTCUSDT,ETHUSDT}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.0}"

# name|strategy|symbols
CANDIDATES="${CANDIDATES:-donchian|donchian_breakout|$SYMBOLS_ALL;range_bounce|range_bounce|$SYMBOLS_ALL;vol_exp|btc_eth_vol_expansion|$SYMBOLS_BTCETH;rsi_reentry|btc_eth_trend_rsi_reentry|$SYMBOLS_BTCETH;trend_follow_v1|btc_eth_trend_follow|$SYMBOLS_BTCETH}"

RUNSET_DIR="backtest_runs/candidate_scan_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"
SUMMARY="$RUNSET_DIR/summary.csv"

echo "name,strategy,cost,tag,ending_equity,trades,net_pnl,pf,winrate,max_dd,run_dir" > "$SUMMARY"

echo "candidate scan start: $(date -u '+%F %T UTC')" | tee "$REPORT"
echo "days=$DAYS end_date=$END_DATE" | tee -a "$REPORT"

auto_case() {
  local name="$1"
  local strategy="$2"
  local symbols="$3"
  local cost="$4"
  local fee="$5"
  local slip="$6"
  local tag="cand_${name}_${cost}_${DAYS}d"

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  BYBIT_DATA_POLITE_SLEEP_SEC="$POLITE_SLEEP" \
  python3 backtest/run_portfolio.py \
    --symbols "$symbols" \
    --strategies "$strategy" \
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

  local row ending trades net pf win maxdd
  row="$(tail -n 1 "$run_dir/summary.csv")"
  ending="$(echo "$row" | cut -d, -f7)"
  trades="$(echo "$row" | cut -d, -f8)"
  net="$(echo "$row" | cut -d, -f9)"
  pf="$(echo "$row" | cut -d, -f10)"
  win="$(echo "$row" | cut -d, -f11)"
  maxdd="$(echo "$row" | cut -d, -f14)"
  echo "${name},${strategy},${cost},${tag},${ending},${trades},${net},${pf},${win},${maxdd},${run_dir}" >> "$SUMMARY"
}

IFS=';' read -r -a ARR <<< "$CANDIDATES"
for item in "${ARR[@]}"; do
  [[ -z "$item" ]] && continue
  IFS='|' read -r name strategy symbols <<< "$item"
  auto_case "$name" "$strategy" "$symbols" base 6 2
  auto_case "$name" "$strategy" "$symbols" stress 10 10
done

echo "" | tee -a "$REPORT"
echo "=== RANK (stress net desc) ===" | tee -a "$REPORT"
SUMMARY_PATH="$SUMMARY" python3 - <<'PY' | tee -a "$REPORT"
import csv, os
rows=[]
with open(os.environ['SUMMARY_PATH'], newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        if row['cost']!='stress':
            continue
        try: row['_net']=float(row['net_pnl'])
        except: row['_net']=-1e18
        rows.append(row)
rows.sort(key=lambda x:x['_net'], reverse=True)
for x in rows:
    print(f"{x['name']:>14} net={x['net_pnl']} pf={x['pf']} trades={x['trades']} dd={x['max_dd']}")
PY

echo "" | tee -a "$REPORT"
echo "candidate scan done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "summary=$SUMMARY" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"
