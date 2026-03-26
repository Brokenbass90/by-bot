#!/usr/bin/env bash
set -euo pipefail

# Candidate scan v2:
# focuses on strategies that were not covered by the previous scan.
# Runs base + stress costs and ranks by stress net.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

END_DATE="${END_DATE:-2026-03-01}"
DAYS="${DAYS:-180}"
SYMBOLS_ALL="${SYMBOLS_ALL:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,AVAXUSDT}"
SYMBOLS_GRID="${SYMBOLS_GRID:-BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.005}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
POLITE_SLEEP="${BYBIT_DATA_POLITE_SLEEP_SEC:-2.0}"
RETRY_MAX="${RETRY_MAX:-3}"
RETRY_SLEEP_SEC="${RETRY_SLEEP_SEC:-30}"

# name|strategy|symbols|extra_env
CANDIDATES="${CANDIDATES:-momentum|momentum|$SYMBOLS_ALL|MOMO_MOVE_THRESHOLD_PCT=0.70 MOMO_PULLBACK_MAX_PCT=0.45 MOMO_COOLDOWN_BARS=8;trend_pullback|trend_pullback|$SYMBOLS_ALL|TPB_MAX_SIGNALS_PER_DAY=3 TPB_COOLDOWN_BARS=8;trend_breakout|trend_breakout|$SYMBOLS_ALL|TRB_MIN_GAP_PCT=0.20 TRB_BREAK_ATR_MULT=0.12 TRB_COOLDOWN_BARS=8;vol_breakout|vol_breakout|$SYMBOLS_ALL|VBR_ATR_MULT=1.25 VBR_BREAK_ATR_MULT=0.08 VBR_COOLDOWN_BARS=8;adaptive_range_short|adaptive_range_short|$SYMBOLS_ALL|ARS_ALLOW_COUNTERTREND=0 ARS_MAX_SIGNALS_PER_DAY=3;smart_grid|smart_grid|$SYMBOLS_GRID|SG_ALLOW_LONGS=1 SG_ALLOW_SHORTS=1;inplay_pullback|inplay_pullback|$SYMBOLS_ALL|PULLBACK_ALLOW_SHORTS=1 PULLBACK_IMPULSE_ATR_MULT=0.65 PULLBACK_MAX_WAIT_BARS=18}"

RUNSET_DIR="backtest_runs/candidate_scan_v2_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNSET_DIR"
REPORT="$RUNSET_DIR/report.txt"
SUMMARY="$RUNSET_DIR/summary.csv"

echo "name,strategy,cost,tag,ending_equity,trades,net_pnl,pf,winrate,max_dd,run_dir" > "$SUMMARY"

echo "candidate scan v2 start: $(date -u '+%F %T UTC')" | tee "$REPORT"
echo "days=$DAYS end_date=$END_DATE" | tee -a "$REPORT"

run_case() {
  local name="$1"
  local strategy="$2"
  local symbols="$3"
  local extra_env="$4"
  local cost="$5"
  local fee="$6"
  local slip="$7"

  local tag="cand2_${name}_${cost}_${DAYS}d"

  echo "" | tee -a "$REPORT"
  echo ">>> RUN $tag" | tee -a "$REPORT"

  local -a env_args=()
  if [[ -n "$extra_env" ]]; then
    # Split KEY=VAL pairs by spaces.
    # shellcheck disable=SC2206
    env_args=($extra_env)
  fi

  local ok=0
  local attempt
  for attempt in $(seq 1 "$RETRY_MAX"); do
    if env "${env_args[@]}" \
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
        --slippage_bps "$slip" | tee -a "$REPORT"; then
      ok=1
      break
    fi
    if [[ "$attempt" -lt "$RETRY_MAX" ]]; then
      local wait_sec=$(( RETRY_SLEEP_SEC * attempt ))
      echo "retry $attempt/$RETRY_MAX for $tag after ${wait_sec}s (likely rate-limit)" | tee -a "$REPORT"
      sleep "$wait_sec"
    fi
  done

  if [[ "$ok" -ne 1 ]]; then
    echo "FAILED $tag after $RETRY_MAX attempts" | tee -a "$REPORT"
    echo "${name},${strategy},${cost},${tag},,,,,,FAILED" >> "$SUMMARY"
    return 0
  fi

  local run_dir
  run_dir="$(ls -1dt backtest_runs/*"${tag}" 2>/dev/null | head -n 1 || true)"
  if [[ -z "$run_dir" ]]; then
    echo "FAILED $tag: run_dir not found" | tee -a "$REPORT"
    echo "${name},${strategy},${cost},${tag},,,,,,NO_RUN_DIR" >> "$SUMMARY"
    return 0
  fi
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
  IFS='|' read -r name strategy symbols extra_env <<< "$item"
  run_case "$name" "$strategy" "$symbols" "$extra_env" base 6 2
  run_case "$name" "$strategy" "$symbols" "$extra_env" stress 10 10
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
        try:
            row['_net']=float(row['net_pnl'])
        except Exception:
            row['_net']=-1e18
        rows.append(row)
rows.sort(key=lambda x:x['_net'], reverse=True)
for x in rows:
    print(f"{x['name']:>18} net={x['net_pnl']} pf={x['pf']} trades={x['trades']} dd={x['max_dd']}")
PY

echo "" | tee -a "$REPORT"
echo "candidate scan v2 done: $(date -u '+%F %T UTC')" | tee -a "$REPORT"
echo "summary=$SUMMARY" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"
