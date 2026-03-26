#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PAIRS_CSV="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}"
DATA_DIR="${FX_DATA_DIR:-data_cache/forex}"
SESSION_START="${FX_SESSION_START_UTC:-6}"
SESSION_END="${FX_SESSION_END_UTC:-20}"

OUT_DIR="backtest_runs/forex_scan_$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/summary.csv"
echo "pair,preset,status,trades,winrate,net_pips,gross_pips,max_dd_pips,run_dir,error" > "$SUMMARY"

_spread_default() {
  case "$1" in
    EURUSD) echo "1.0" ;;
    GBPUSD) echo "1.2" ;;
    USDJPY) echo "1.0" ;;
    *) echo "1.2" ;;
  esac
}

_swap_default() {
  case "$1" in
    EURUSD) echo "-0.3" ;;
    GBPUSD) echo "-0.4" ;;
    USDJPY) echo "-0.2" ;;
    *) echo "-0.2" ;;
  esac
}

run_one() {
  local pair="$1"
  local preset="$2"
  local ema_fast="$3"
  local ema_slow="$4"
  local brk_lb="$5"
  local retest_w="$6"
  local sl_mult="$7"
  local rr="$8"
  local cooldown="$9"

  local csv_path="${DATA_DIR}/${pair}_M5.csv"
  if [[ ! -f "$csv_path" ]]; then
    echo "${pair},${preset},skip,0,0,0,0,0,,missing_csv" >> "$SUMMARY"
    return
  fi

  local spread_var="FX_${pair}_SPREAD"
  local swap_long_var="FX_${pair}_SWAP_LONG"
  local swap_short_var="FX_${pair}_SWAP_SHORT"
  local spread="${!spread_var-}"
  local swap_long="${!swap_long_var-}"
  local swap_short="${!swap_short_var-}"
  [[ -z "$spread" ]] && spread="$(_spread_default "$pair")"
  [[ -z "$swap_long" ]] && swap_long="$(_swap_default "$pair")"
  [[ -z "$swap_short" ]] && swap_short="$(_swap_default "$pair")"

  local tag="scan_${pair}_${preset}_$(date -u +%Y%m%d_%H%M%S)"
  local log="$OUT_DIR/${pair}_${preset}.log"

  if python3 scripts/run_forex_backtest.py \
      --symbol "$pair" \
      --csv "$csv_path" \
      --tag "$tag" \
      --spread_pips "$spread" \
      --swap_long "$swap_long" \
      --swap_short "$swap_short" \
      --session_start_utc "$SESSION_START" \
      --session_end_utc "$SESSION_END" \
      --ema_fast "$ema_fast" \
      --ema_slow "$ema_slow" \
      --breakout_lookback "$brk_lb" \
      --retest_window_bars "$retest_w" \
      --sl_atr_mult "$sl_mult" \
      --rr "$rr" \
      --cooldown_bars "$cooldown" > "$log" 2>&1; then
    local run_dir
    run_dir="$(grep -E '^saved=' "$log" | tail -n 1 | cut -d= -f2-)"
    if [[ -z "$run_dir" ]]; then
      run_dir="$(ls -1dt backtest_runs/forex_scan_${pair}_${preset}_* 2>/dev/null | head -n 1)"
    fi
    local metrics
    metrics="$(python3 - "$run_dir/summary.csv" <<'PY'
import csv, sys
with open(sys.argv[1], newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    row = next(r, {})
print(
    "{},{},{},{}".format(
        row.get("trades", "0"),
        row.get("winrate", "0"),
        row.get("net_pips", "0"),
        row.get("gross_pips", "0"),
    )
    + "," + row.get("max_dd_pips", "0")
)
PY
)"
    local trades win net gross dd
    IFS=',' read -r trades win net gross dd <<< "$metrics"
    echo "${pair},${preset},ok,${trades},${win},${net},${gross},${dd},${run_dir}," >> "$SUMMARY"
  else
    local err
    err="$(tail -n 1 "$log" | tr ',' ';')"
    echo "${pair},${preset},fail,0,0,0,0,0,,${err}" >> "$SUMMARY"
  fi
}

echo "forex strategy scan start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS_CSV}"
echo "data_dir=${DATA_DIR}"
echo "session_utc=[${SESSION_START},${SESSION_END})"
echo "out_dir=${OUT_DIR}"

IFS=',' read -r -a PAIRS <<< "$PAIRS_CSV"
for raw in "${PAIRS[@]}"; do
  pair="$(echo "$raw" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  [[ -z "$pair" ]] && continue
  echo ""
  echo ">>> ${pair}"
  # preset, ema_fast, ema_slow, breakout_lookback, retest_window_bars, sl_atr_mult, rr, cooldown_bars
  run_one "$pair" "conservative" 55 220 42 8 1.4 2.5 32
  run_one "$pair" "balanced"     48 200 36 6 1.5 2.2 24
  run_one "$pair" "active"       34 144 24 5 1.6 1.9 14
done

echo ""
echo "=== RANK (net_pips desc) ==="
python3 - "$SUMMARY" <<'PY'
import csv, sys
from pathlib import Path
p = Path(sys.argv[1])
rows = []
with p.open(newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        if row.get("status") != "ok":
            continue
        try:
            row["_net"] = float(row.get("net_pips") or 0.0)
        except Exception:
            row["_net"] = -1e18
        rows.append(row)
rows.sort(key=lambda x: x["_net"], reverse=True)
for row in rows:
    print(
        f"{row['pair']:>7} {row['preset']:>12} "
        f"net={row['net_pips']} trades={row['trades']} win={row['winrate']} dd={row['max_dd_pips']}"
    )
if not rows:
    print("no successful runs")
PY

echo ""
echo "forex strategy scan done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "summary=${SUMMARY}"
