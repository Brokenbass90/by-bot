#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

TS_UTC="$(date -u +%Y%m%d_%H%M%S)"
OUT_DIR="backtest_runs/funding_leverage_sweep_${TS_UTC}"
mkdir -p "$OUT_DIR"
CSV="$OUT_DIR/summary.csv"

echo "leverage,notional_per_symbol,base_net,stress_net,base_top_share,stress_top_share,report" > "$CSV"

# Defaults tuned to realistic profile.
LEVERAGES="${FUNDING_SWEEP_LEVERAGES:-1.0 1.5 2.0 3.0}"
BASE_NOTIONAL="${FUNDING_BASE_NOTIONAL:-25}"
TOP_N="${FUNDING_TOP_N:-4}"
SYMBOLS="${FUNDING_SYMBOLS:-HYPEUSDT,1000PEPEUSDT,ETHUSDT,SOLUSDT}"

for LEV in $LEVERAGES; do
  NOTIONAL="$(awk -v b="$BASE_NOTIONAL" -v l="$LEV" 'BEGIN{printf "%.2f", b*l}')"

  echo ""
  echo ">>> leverage=${LEV}x notional_per_symbol=${NOTIONAL}"

  set +e
  FUNDING_TOP_N="$TOP_N" \
  FUNDING_SYMBOLS="$SYMBOLS" \
  FUNDING_NOTIONAL="$NOTIONAL" \
  FUNDING_MIN_TURNOVER_USD="${FUNDING_MIN_TURNOVER_USD:-150000000}" \
  FUNDING_MIN_OI_USD="${FUNDING_MIN_OI_USD:-30000000}" \
  FUNDING_MIN_ABS_FR_PCT="${FUNDING_MIN_ABS_FR_PCT:-0.005}" \
  FUNDING_MAX_ABS_FR_PCT="${FUNDING_MAX_ABS_FR_PCT:-0.25}" \
  FUNDING_MIN_EVENTS="${FUNDING_MIN_EVENTS:-120}" \
  FUNDING_MIN_INTERVAL_H="${FUNDING_MIN_INTERVAL_H:-6}" \
  FUNDING_MAX_INTERVAL_H="${FUNDING_MAX_INTERVAL_H:-10}" \
  FUNDING_MIN_SYMBOL_NET="${FUNDING_MIN_SYMBOL_NET:-0.00}" \
  FUNDING_MAX_TOP_SHARE="${FUNDING_MAX_TOP_SHARE:-0.45}" \
  bash scripts/run_funding_gate_overnight.sh
  RC=$?
  set -e

  REP="$(ls -1dt backtest_runs/funding_gate_ab_* | head -n1)/report.txt"

  if [[ $RC -ne 0 || ! -f "$REP" ]]; then
    echo "${LEV},${NOTIONAL},fail,fail,fail,fail,${REP}" >> "$CSV"
    continue
  fi

  BASE_NET="$(grep '^funding_gate_base_' "$REP" | head -n1 | cut -d, -f18)"
  STRESS_NET="$(grep '^funding_gate_stress_' "$REP" | head -n1 | cut -d, -f18)"
  BASE_TOP="$(grep '^funding_gate_base_' "$REP" | head -n1 | cut -d, -f19)"
  STRESS_TOP="$(grep '^funding_gate_stress_' "$REP" | head -n1 | cut -d, -f19)"

  echo "${LEV},${NOTIONAL},${BASE_NET},${STRESS_NET},${BASE_TOP},${STRESS_TOP},${REP}" >> "$CSV"
done

echo ""
echo "saved=${CSV}"
cat "$CSV"
