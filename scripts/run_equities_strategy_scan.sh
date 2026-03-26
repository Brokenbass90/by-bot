#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TICKERS_CSV="${EQ_TICKERS:-AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM}"
DATA_DIR="${EQ_DATA_DIR:-data_cache/equities}"
SESSION_START="${EQ_SESSION_START_UTC:-14}"
SESSION_END="${EQ_SESSION_END_UTC:-21}"
BASE_SPREAD_CENTS="${EQ_BASE_SPREAD_CENTS:-2.0}"
STRESS_SPREAD_CENTS="${EQ_STRESS_SPREAD_CENTS:-3.5}"
PIP_SIZE="${EQ_PIP_SIZE:-0.01}"        # 1 pip = 1 cent
MIN_TRADES="${EQ_MIN_TRADES:-20}"

OUT_DIR="backtest_runs/equities_scan_$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/summary.csv"
echo "ticker,strategy,base_status,stress_status,base_trades,stress_trades,base_net_cents,stress_net_cents,base_dd_cents,stress_dd_cents,base_run,stress_run,error" > "$SUMMARY"

run_one() {
  local ticker="$1"
  local strategy="$2"
  local csv_path="${DATA_DIR}/${ticker}_M5.csv"
  if [[ ! -f "$csv_path" ]]; then
    echo "${ticker},${strategy},skip,skip,0,0,0,0,0,0,,,missing_csv" >> "$SUMMARY"
    return
  fi

  local base_tag="eq_${ticker}_${strategy}_base_$(date -u +%Y%m%d_%H%M%S)"
  local stress_tag="eq_${ticker}_${strategy}_stress_$(date -u +%Y%m%d_%H%M%S)"
  local base_log="$OUT_DIR/${ticker}_${strategy}_base.log"
  local stress_log="$OUT_DIR/${ticker}_${strategy}_stress.log"

  local base_status="ok"
  local stress_status="ok"
  local err=""

  python3 scripts/run_forex_backtest.py \
    --symbol "$ticker" \
    --csv "$csv_path" \
    --tag "$base_tag" \
    --strategy "$strategy" \
    --spread_pips "$BASE_SPREAD_CENTS" \
    --swap_long "0" \
    --swap_short "0" \
    --pip_size "$PIP_SIZE" \
    --session_start_utc "$SESSION_START" \
    --session_end_utc "$SESSION_END" > "$base_log" 2>&1 || base_status="fail"

  python3 scripts/run_forex_backtest.py \
    --symbol "$ticker" \
    --csv "$csv_path" \
    --tag "$stress_tag" \
    --strategy "$strategy" \
    --spread_pips "$STRESS_SPREAD_CENTS" \
    --swap_long "0" \
    --swap_short "0" \
    --pip_size "$PIP_SIZE" \
    --session_start_utc "$SESSION_START" \
    --session_end_utc "$SESSION_END" > "$stress_log" 2>&1 || stress_status="fail"

  local base_run="" stress_run=""
  local base_trades=0 stress_trades=0
  local base_net=0 stress_net=0
  local base_dd=0 stress_dd=0

  if [[ "$base_status" == "ok" ]]; then
    base_run="$(grep -E '^saved=' "$base_log" | tail -n 1 | cut -d= -f2-)"
    if [[ -f "${base_run}/summary.csv" ]]; then
      read -r base_trades base_net base_dd <<<"$(python3 - "${base_run}/summary.csv" <<'PY'
import csv,sys
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    r=csv.DictReader(f); row=next(r,{})
print(f"{row.get('trades','0')} {row.get('net_pips','0')} {row.get('max_dd_pips','0')}")
PY
)"
    fi
  else
    err+="base_fail;"
  fi

  if [[ "$stress_status" == "ok" ]]; then
    stress_run="$(grep -E '^saved=' "$stress_log" | tail -n 1 | cut -d= -f2-)"
    if [[ -f "${stress_run}/summary.csv" ]]; then
      read -r stress_trades stress_net stress_dd <<<"$(python3 - "${stress_run}/summary.csv" <<'PY'
import csv,sys
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    r=csv.DictReader(f); row=next(r,{})
print(f"{row.get('trades','0')} {row.get('net_pips','0')} {row.get('max_dd_pips','0')}")
PY
)"
    fi
  else
    err+="stress_fail;"
  fi

  echo "${ticker},${strategy},${base_status},${stress_status},${base_trades},${stress_trades},${base_net},${stress_net},${base_dd},${stress_dd},${base_run},${stress_run},${err}" >> "$SUMMARY"
}

echo "equities strategy scan start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "tickers=${TICKERS_CSV}"
echo "data_dir=${DATA_DIR}"
echo "session_utc=[${SESSION_START},${SESSION_END})"
echo "out_dir=${OUT_DIR}"

IFS=',' read -r -a TICKERS <<< "$TICKERS_CSV"
for raw in "${TICKERS[@]}"; do
  ticker="$(echo "$raw" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  [[ -z "$ticker" ]] && continue
  echo ""
  echo ">>> ${ticker}"
  run_one "$ticker" "trend_retest_session_v1"
  run_one "$ticker" "trend_retest_session_v1:quality_guard"
  run_one "$ticker" "range_bounce_session_v1"
  run_one "$ticker" "breakout_continuation_session_v1"
  run_one "$ticker" "breakout_continuation_session_v1:quality_guard"
  run_one "$ticker" "grid_reversion_session_v1"
  run_one "$ticker" "grid_reversion_session_v1:safe_winrate"
  run_one "$ticker" "trend_pullback_rebound_v1"
  run_one "$ticker" "trend_pullback_rebound_v1:quality_guard"
done

echo ""
echo "=== GATE PASS (stress_net_cents desc) ==="
python3 - "$SUMMARY" "$MIN_TRADES" <<'PY'
import csv,sys
from pathlib import Path
p=Path(sys.argv[1]); min_trades=float(sys.argv[2])
rows=[]
with p.open(newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        if row.get("base_status")!="ok" or row.get("stress_status")!="ok":
            continue
        bt=float(row.get("base_trades") or 0)
        st=float(row.get("stress_trades") or 0)
        bn=float(row.get("base_net_cents") or 0)
        sn=float(row.get("stress_net_cents") or 0)
        if bt < min_trades or st < min_trades:
            continue
        if bn <= 0 or sn <= 0:
            continue
        row["_sn"]=sn
        rows.append(row)
rows.sort(key=lambda x:x["_sn"], reverse=True)
if not rows:
    print("no ticker+strategy passed current gate")
else:
    for row in rows:
        print(f"{row['ticker']:>6} {row['strategy']:<32} base={float(row['base_net_cents']):+8.2f} stress={float(row['stress_net_cents']):+8.2f} trades={int(float(row['stress_trades'])):4d} dd={float(row['stress_dd_cents']):8.2f}")
PY

echo ""
echo "equities strategy scan done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "summary=${SUMMARY}"
