#!/usr/bin/env bash
set -euo pipefail

# Runs a small matrix of live-parity replays for breakout profile tuning.
# Output: compact table with stress/base trades and net for each profile.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

DAYS="${DAYS:-2}"
AUTO_SYMBOLS="${AUTO_SYMBOLS:-1}"
TOP_N="${TOP_N:-16}"
QUALITY_MIN_BASE="${QUALITY_MIN_BASE:-0.52}"
IMPULSE_ATR_BASE="${IMPULSE_ATR_BASE:-0.75}"
IMPULSE_BODY_BASE="${IMPULSE_BODY_BASE:-0.40}"
MAX_CHASE="${MAX_CHASE:-0.22}"
MAX_LATE="${MAX_LATE:-0.55}"
MIN_PULLBACK="${MIN_PULLBACK:-0.03}"
# Keep parity-matrix runs responsive when Bybit connectivity is degraded.
BYBIT_DATA_MAX_RETRIES="${BYBIT_DATA_MAX_RETRIES:-3}"
BYBIT_DATA_BACKOFF_MAX_SEC="${BYBIT_DATA_BACKOFF_MAX_SEC:-4.0}"
BYBIT_DATA_BACKOFF_MULT="${BYBIT_DATA_BACKOFF_MULT:-1.5}"
BYBIT_DATA_RETRY_JITTER_SEC="${BYBIT_DATA_RETRY_JITTER_SEC:-0.15}"
BYBIT_DATA_POLITE_SLEEP_SEC="${BYBIT_DATA_POLITE_SLEEP_SEC:-0.15}"

echo "live parity matrix start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "days=${DAYS} auto_symbols=${AUTO_SYMBOLS} top_n=${TOP_N}"

TMP_CSV="$(mktemp)"
echo "profile,quality_min,impulse_atr,impulse_body,base_trades,base_net,stress_trades,stress_net,stress_pf,stress_winrate,stress_dd" > "$TMP_CSV"
LATEST_CSV="docs/live_parity_matrix_latest.csv"
mkdir -p "$(dirname "$LATEST_CSV")"
cp "$TMP_CSV" "$LATEST_CSV"

run_profile() {
  local profile="$1"
  local qmin="$2"
  local iatr="$3"
  local ibody="$4"
  local slog="/tmp/live_parity_matrix_${profile}.log"

  echo ""
  echo ">>> PROFILE ${profile} (q=${qmin} atr=${iatr} body=${ibody})"

  if ! QUALITY_MIN="$qmin" \
    IMPULSE_ATR_MULT="$iatr" \
    IMPULSE_BODY_MIN_FRAC="$ibody" \
    MAX_CHASE="$MAX_CHASE" \
    MAX_LATE="$MAX_LATE" \
    MIN_PULLBACK="$MIN_PULLBACK" \
    BYBIT_DATA_MAX_RETRIES="$BYBIT_DATA_MAX_RETRIES" \
    BYBIT_DATA_BACKOFF_MAX_SEC="$BYBIT_DATA_BACKOFF_MAX_SEC" \
    BYBIT_DATA_BACKOFF_MULT="$BYBIT_DATA_BACKOFF_MULT" \
    BYBIT_DATA_RETRY_JITTER_SEC="$BYBIT_DATA_RETRY_JITTER_SEC" \
    BYBIT_DATA_POLITE_SLEEP_SEC="$BYBIT_DATA_POLITE_SLEEP_SEC" \
    DAYS="$DAYS" \
    AUTO_SYMBOLS="$AUTO_SYMBOLS" \
    TOP_N="$TOP_N" \
    bash scripts/run_live_parity_backtest.sh >"$slog" 2>&1; then
    echo "${profile},${qmin},${iatr},${ibody},0,0,0,0,0,0,0" >> "$TMP_CSV"
    echo "WARN: profile ${profile} failed (see ${slog})"
    return
  fi

  local base_run
  local stress_run
  base_run="$(ls -1dt backtest_runs/*live_parity_base_"${DAYS}"d 2>/dev/null | head -n 1 || true)"
  stress_run="$(ls -1dt backtest_runs/*live_parity_stress_"${DAYS}"d 2>/dev/null | head -n 1 || true)"

  if [[ -z "${base_run}" || -z "${stress_run}" ]]; then
    echo "${profile},${qmin},${iatr},${ibody},0,0,0,0,0,0,0" >> "$TMP_CSV"
    echo "WARN: missing run dirs for ${profile}"
    return
  fi

  python3 - <<'PY' "$profile" "$qmin" "$iatr" "$ibody" "$base_run/summary.csv" "$stress_run/summary.csv" "$TMP_CSV"
import csv, sys
profile, qmin, iatr, ibody, base_path, stress_path, out_path = sys.argv[1:]

def read_one(path):
    with open(path, newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    return row

b = read_one(base_path)
s = read_one(stress_path)

line = ",".join([
    profile,
    qmin,
    iatr,
    ibody,
    str(b.get("trades", "0")),
    str(b.get("net_pnl", "0")),
    str(s.get("trades", "0")),
    str(s.get("net_pnl", "0")),
    str(s.get("profit_factor", "0")),
    str(s.get("winrate", "0")),
    str(s.get("max_drawdown", "0")),
])
with open(out_path, "a", encoding="utf-8") as f:
    f.write(line + "\n")
PY
  cp "$TMP_CSV" "$LATEST_CSV"
}

# baseline + two canary relaxations
run_profile "baseline" "${QUALITY_MIN_BASE}" "${IMPULSE_ATR_BASE}" "${IMPULSE_BODY_BASE}"
run_profile "canary_soft" "${QUALITY_MIN_SOFT:-0.50}" "${IMPULSE_ATR_SOFT:-0.70}" "${IMPULSE_BODY_SOFT:-0.35}"
run_profile "canary_loose" "${QUALITY_MIN_LOOSE:-0.48}" "${IMPULSE_ATR_LOOSE:-0.65}" "${IMPULSE_BODY_LOOSE:-0.30}"

OUT_DIR="backtest_runs/live_parity_matrix_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
cp "$TMP_CSV" "$OUT_DIR/summary.csv"
cp "$TMP_CSV" "$LATEST_CSV"

echo ""
echo "=== MATRIX SUMMARY ==="
cat "$TMP_CSV"
echo ""
echo "saved=$OUT_DIR/summary.csv"
echo "latest=$LATEST_CSV"
echo "live parity matrix done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
rm -f "$TMP_CSV"
