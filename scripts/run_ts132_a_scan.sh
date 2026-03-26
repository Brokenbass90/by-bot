#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

# Friend A-list from screenshot (can override via env TS132_A_SYMBOLS)
SYMS_CSV="${TS132_A_SYMBOLS:-AXSUSDT,KASUSDT,APEUSDT,AIXBUSDT,KSMUSDT,ARBUSDT,STRKUSDT,NEARUSDT}"
IFS=',' read -r -a SYMS <<< "$SYMS_CSV"

END_DATE="${TS132_END_DATE:-2026-03-01}"
DAYS="${TS132_DAYS:-180}"
OUT="backtest_runs/ts132_a_scan_$(date +%Y%m%d_%H%M%S).csv"
echo "symbol,mode,status,run_dir,net,pf,trades,winrate,max_dd,error" > "$OUT"

run_one() {
  local sym="$1"
  local mode="$2"
  local tag="ts132_a_${sym}_${mode}_${DAYS}d"
  local fees slippage exec_mode
  if [[ "$mode" == "base" ]]; then
    fees=6; slippage=2; exec_mode="optimistic"
  else
    fees=10; slippage=10; exec_mode="alts"
  fi

  local log="/tmp/${tag}.log"
  local tries=0
  local max_tries=4
  local ok=0
  while (( tries < max_tries )); do
    tries=$((tries+1))
    if BYBIT_DATA_POLITE_SLEEP_SEC=2.5 \
      TS132_TRADE_MODE=conservative \
      TS132_OSC_TYPE=rsi \
      TS132_EVAL_TF_MIN=60 \
      TS132_USE_VOL_FILTER=1 \
      TS132_VOL_MULT=1.0 \
      TS132_MAX_SIGNALS_PER_DAY=1 \
      TS132_EXEC_MODE="$exec_mode" \
      python3 backtest/run_portfolio.py \
        --symbols "$sym" \
        --strategies triple_screen_v132 \
        --days "$DAYS" --end "$END_DATE" \
        --tag "$tag" \
        --starting_equity 100 --risk_pct 0.005 --leverage 3 --max_positions 1 \
        --fee_bps "$fees" --slippage_bps "$slippage" >"$log" 2>&1; then
      ok=1
      break
    fi
    if grep -Eqi "error 10006|Too many visits|rate limit" "$log"; then
      sleep 70
      continue
    fi
    break
  done

  if (( ok == 1 )); then
    local run_dir
    run_dir="$(awk -F': ' '/Saved portfolio run to/{print $2}' "$log" | tail -n1)"
    if [[ -n "$run_dir" && -f "$run_dir/summary.csv" ]]; then
      awk -F, -v sym="$sym" -v md="$mode" -v rd="$run_dir" 'NR==2{printf "%s,%s,ok,%s,%s,%s,%s,%s,%s,\n",sym,md,rd,$9,$10,$8,$11,$14}' "$run_dir/summary.csv" >> "$OUT"
    else
      echo "${sym},${mode},ok_no_summary,,,,,,," >> "$OUT"
    fi
  else
    local err
    err="$(tail -n 1 "$log" | tr ',' ';' | cut -c1-220)"
    echo "${sym},${mode},fail,,,,,,,${err}" >> "$OUT"
  fi
}

for s in "${SYMS[@]}"; do
  run_one "$s" "base"
  run_one "$s" "stress"
done

echo "saved=$OUT"
cat "$OUT"
