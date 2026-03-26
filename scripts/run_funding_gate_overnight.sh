#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TS_UTC="$(date -u +%Y%m%d_%H%M%S)"
OUT_DIR="backtest_runs/funding_gate_ab_${TS_UTC}"
mkdir -p "$OUT_DIR"
REPORT="$OUT_DIR/report.txt"

# Defaults (override via env)
DAYS="${FUNDING_DAYS:-180}"
END_DATE="${FUNDING_END_DATE:-$(date -u +%Y-%m-%d)}"
TOP_N="${FUNDING_TOP_N:-8}"
NOTIONAL="${FUNDING_NOTIONAL:-100}"
FIXED_SYMBOLS="${FUNDING_SYMBOLS:-}"

# Selection / robustness
MIN_TURNOVER="${FUNDING_MIN_TURNOVER_USD:-20000000}"
MIN_OI="${FUNDING_MIN_OI_USD:-5000000}"
MIN_ABS_FR="${FUNDING_MIN_ABS_FR_PCT:-0.003}"
MAX_ABS_FR="${FUNDING_MAX_ABS_FR_PCT:-2.0}"
MIN_EVENTS="${FUNDING_MIN_EVENTS:-120}"
MIN_INTERVAL_H="${FUNDING_MIN_INTERVAL_H:-6}"
MAX_INTERVAL_H="${FUNDING_MAX_INTERVAL_H:-10}"
CLIP_RATE="${FUNDING_CLIP_RATE:-0.008}"
MAX_TOP_SHARE="${FUNDING_MAX_TOP_SHARE:-0.45}"
MIN_SYMBOL_NET="${FUNDING_MIN_SYMBOL_NET:--0.10}"
SEL_BUFFER="${FUNDING_SELECTION_BUFFER_MULT:-10}"

# Costs
BASE_PERP_FEE="${FUNDING_BASE_PERP_FEE_BPS:-6}"
BASE_SPOT_FEE="${FUNDING_BASE_SPOT_FEE_BPS:-10}"
STRESS_PERP_FEE="${FUNDING_STRESS_PERP_FEE_BPS:-10}"
STRESS_SPOT_FEE="${FUNDING_STRESS_SPOT_FEE_BPS:-20}"

echo "funding gate A/B start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee "$REPORT"
echo "days=$DAYS end_date=$END_DATE top_n=$TOP_N notional=$NOTIONAL" | tee -a "$REPORT"
if [[ -n "$FIXED_SYMBOLS" ]]; then
  echo "fixed_symbols=$FIXED_SYMBOLS" | tee -a "$REPORT"
fi
echo "filters: turnover>=$MIN_TURNOVER oi>=$MIN_OI abs_fr=[${MIN_ABS_FR},${MAX_ABS_FR}] events>=$MIN_EVENTS interval=[${MIN_INTERVAL_H},${MAX_INTERVAL_H}] clip=$CLIP_RATE" | tee -a "$REPORT"
echo "selector: max_top_share=$MAX_TOP_SHARE min_symbol_net=$MIN_SYMBOL_NET selection_buffer_mult=$SEL_BUFFER" | tee -a "$REPORT"

if END_SEC="$(date -u -j -f '%Y-%m-%d' "$END_DATE" '+%s' 2>/dev/null)"; then
  :
elif END_SEC="$(date -u -d "$END_DATE" +%s 2>/dev/null)"; then
  :
else
  echo "Invalid END_DATE=$END_DATE (expected YYYY-MM-DD)" | tee -a "$REPORT"
  exit 2
fi
END_MS="$(( END_SEC * 1000 ))"

# Network preflight: avoid long stacktraces when DNS/internet is down.
check_network() {
  python3 - <<'PY'
import socket, sys
try:
    socket.getaddrinfo("api.bybit.com", 443)
except Exception:
    sys.exit(1)
sys.exit(0)
PY
}

NET_OK=0
for i in 1 2 3 4 5; do
  if check_network; then
    NET_OK=1
    break
  fi
  sleep 3
done
if [[ "$NET_OK" != "1" ]]; then
  echo "Network/DNS preflight failed: cannot resolve api.bybit.com. Abort run." | tee -a "$REPORT"
  echo "Hint: retry when internet is stable or switch network (e.g., mobile hotspot)." | tee -a "$REPORT"
  echo "report=$REPORT" | tee -a "$REPORT"
  exit 3
fi

auto_run() {
  local mode="$1" perp_fee="$2" spot_fee="$3" tag="$4"
  printf "\n>>> RUN %s\n" "$tag" | tee -a "$REPORT"
  local log="/tmp/${tag}.log"
  if python3 scripts/backtest_funding_capture.py \
      --days "$DAYS" \
      --end_ms "$END_MS" \
      $([[ -n "$FIXED_SYMBOLS" ]] && printf -- "--symbols %q " "$FIXED_SYMBOLS") \
      $([[ -z "$FIXED_SYMBOLS" ]] && printf -- "--top_n %q --selection_buffer_mult %q " "$TOP_N" "$SEL_BUFFER") \
      --notional_per_symbol "$NOTIONAL" \
      --tag "$tag" \
      --mode "$mode" \
      --min_turnover_usd "$MIN_TURNOVER" \
      --min_oi_usd "$MIN_OI" \
      --min_abs_funding_8h_pct "$MIN_ABS_FR" \
      --max_abs_funding_8h_pct "$MAX_ABS_FR" \
      --min_events_per_symbol "$MIN_EVENTS" \
      --min_interval_hours "$MIN_INTERVAL_H" \
      --max_interval_hours "$MAX_INTERVAL_H" \
      --clip_abs_rate "$CLIP_RATE" \
      --max_top_symbol_share "$MAX_TOP_SHARE" \
      --min_symbol_net_usd "$MIN_SYMBOL_NET" \
      --fee_bps_open_close_perp "$perp_fee" \
      --fee_bps_open_close_spot "$spot_fee" > "$log" 2>&1; then
    local run_dir
    run_dir="$(awk -F': ' '/Saved funding run to/{print $2}' "$log" | tail -n1)"
    echo "run_dir=$run_dir" | tee -a "$REPORT"
    cat "$run_dir/summary.csv" | tee -a "$REPORT"
    # External gate output (same logic, explicit artifact)
    python3 scripts/strategy_symbol_gate.py funding \
      --per_symbol_csv "$run_dir/funding_per_symbol.csv" \
      --top_n "$TOP_N" \
      --min_events "$MIN_EVENTS" \
      --max_top_symbol_share "$MAX_TOP_SHARE" \
      --min_symbol_net_usd "$MIN_SYMBOL_NET" \
      --out_csv "$run_dir/funding_per_symbol_gated.csv" | tee -a "$REPORT"
    echo "gated_symbols=$(awk -F, 'NR>1{print $1}' "$run_dir/funding_per_symbol_gated.csv" | paste -sd',' -)" | tee -a "$REPORT"
    echo "monthly:" | tee -a "$REPORT"
    cat "$run_dir/monthly_pnl.csv" | tee -a "$REPORT"
    local compact
    compact="$(awk -F, 'NR==2{printf "%s,%s,net=%s,top_share=%s,events=%s,symbols=%s",$1,"'"$mode"'",$18,$19,$14,$3}' "$run_dir/summary.csv")"
    echo "compact=$compact" | tee -a "$REPORT"
  else
    echo "FAILED $tag" | tee -a "$REPORT"
    tail -n 60 "$log" | tee -a "$REPORT"
  fi
}

# BASE and STRESS on hold-mode (current winning contour)
auto_run hold "$BASE_PERP_FEE" "$BASE_SPOT_FEE" "funding_gate_base_${DAYS}d"
auto_run hold "$STRESS_PERP_FEE" "$STRESS_SPOT_FEE" "funding_gate_stress_${DAYS}d"

printf "\nfunding gate A/B done: %s\n" "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee -a "$REPORT"
echo "report=$REPORT" | tee -a "$REPORT"
