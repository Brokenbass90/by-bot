#!/usr/bin/env bash
set -euo pipefail

# Runs a small live-parity matrix over TOP_N to measure breakout opportunity
# without relaxing the candle-body guard.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

DAYS="${DAYS:-2}"
AUTO_SYMBOLS="${AUTO_SYMBOLS:-1}"
TOP_N_VALUES="${TOP_N_VALUES:-16,24,32}"
MIN_VOLUME_USD="${MIN_VOLUME_USD:-20000000}"
EXCLUDE_SYMBOLS="${EXCLUDE_SYMBOLS:-${BREAKOUT_SYMBOL_DENYLIST:-}}"

QUALITY_MIN="${QUALITY_MIN:-0.52}"
IMPULSE_ATR_MULT="${IMPULSE_ATR_MULT:-0.75}"
IMPULSE_BODY_MIN_FRAC="${IMPULSE_BODY_MIN_FRAC:-0.40}"
MAX_CHASE="${MAX_CHASE:-0.22}"
MAX_LATE="${MAX_LATE:-0.55}"
MIN_PULLBACK="${MIN_PULLBACK:-0.03}"
RECLAIM_ATR="${RECLAIM_ATR:-0.10}"
MAX_DIST_ATR="${MAX_DIST_ATR:-1.50}"
BUFFER_ATR="${BUFFER_ATR:-0.06}"
ALLOW_SHORTS="${ALLOW_SHORTS:-1}"
REGIME_STRICT="${REGIME_STRICT:-0}"

echo "live parity universe matrix start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "days=${DAYS} top_n_values=${TOP_N_VALUES} auto_symbols=${AUTO_SYMBOLS}"
echo "profile: q=${QUALITY_MIN} atr=${IMPULSE_ATR_MULT} body=${IMPULSE_BODY_MIN_FRAC}"

TMP_CSV="$(mktemp)"
echo "top_n,quality_min,impulse_atr,impulse_body,base_trades,base_net,stress_trades,stress_net,stress_pf,stress_winrate,stress_dd" > "$TMP_CSV"
LATEST_CSV="docs/live_parity_universe_latest.csv"
mkdir -p "$(dirname "$LATEST_CSV")"
cp "$TMP_CSV" "$LATEST_CSV"

run_top_n() {
  local top_n="$1"
  local prefix="livefreq_top${top_n}"
  local slog="/tmp/live_parity_universe_${top_n}.log"

  echo ""
  echo ">>> TOP_N ${top_n}"

  if ! QUALITY_MIN="$QUALITY_MIN" \
    IMPULSE_ATR_MULT="$IMPULSE_ATR_MULT" \
    IMPULSE_BODY_MIN_FRAC="$IMPULSE_BODY_MIN_FRAC" \
    MAX_CHASE="$MAX_CHASE" \
    MAX_LATE="$MAX_LATE" \
    MIN_PULLBACK="$MIN_PULLBACK" \
    RECLAIM_ATR="$RECLAIM_ATR" \
    MAX_DIST_ATR="$MAX_DIST_ATR" \
    BUFFER_ATR="$BUFFER_ATR" \
    ALLOW_SHORTS="$ALLOW_SHORTS" \
    REGIME_STRICT="$REGIME_STRICT" \
    DAYS="$DAYS" \
    AUTO_SYMBOLS="$AUTO_SYMBOLS" \
    TOP_N="$top_n" \
    MIN_VOLUME_USD="$MIN_VOLUME_USD" \
    EXCLUDE_SYMBOLS="$EXCLUDE_SYMBOLS" \
    TAG_PREFIX="$prefix" \
    bash scripts/run_live_parity_backtest.sh >"$slog" 2>&1; then
    echo "${top_n},${QUALITY_MIN},${IMPULSE_ATR_MULT},${IMPULSE_BODY_MIN_FRAC},0,0,0,0,0,0,0" >> "$TMP_CSV"
    echo "WARN: TOP_N ${top_n} failed (see ${slog})"
    cp "$TMP_CSV" "$LATEST_CSV"
    return
  fi

  local base_run=""
  local stress_run=""
  base_run="$(ls -1dt backtest_runs/*"${prefix}"_base_"${DAYS}"d 2>/dev/null | head -n 1 || true)"
  stress_run="$(ls -1dt backtest_runs/*"${prefix}"_stress_"${DAYS}"d 2>/dev/null | head -n 1 || true)"

  if [[ -z "${base_run}" || -z "${stress_run}" ]]; then
    echo "${top_n},${QUALITY_MIN},${IMPULSE_ATR_MULT},${IMPULSE_BODY_MIN_FRAC},0,0,0,0,0,0,0" >> "$TMP_CSV"
    echo "WARN: missing run dirs for TOP_N ${top_n}"
    cp "$TMP_CSV" "$LATEST_CSV"
    return
  fi

  python3 - <<'PY' "$top_n" "$QUALITY_MIN" "$IMPULSE_ATR_MULT" "$IMPULSE_BODY_MIN_FRAC" "$base_run/summary.csv" "$stress_run/summary.csv" "$TMP_CSV"
import csv, sys
top_n, qmin, iatr, ibody, base_path, stress_path, out_path = sys.argv[1:]

def read_one(path):
    with open(path, newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    return row

b = read_one(base_path)
s = read_one(stress_path)

line = ",".join([
    top_n,
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

IFS=',' read -r -a TOPS <<< "$TOP_N_VALUES"
for item in "${TOPS[@]}"; do
  top_n="$(echo "$item" | xargs)"
  [[ -z "$top_n" ]] && continue
  run_top_n "$top_n"
done

OUT_DIR="backtest_runs/live_parity_universe_matrix_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
cp "$TMP_CSV" "$OUT_DIR/summary.csv"
cp "$TMP_CSV" "$LATEST_CSV"

echo ""
echo "=== UNIVERSE MATRIX SUMMARY ==="
cat "$TMP_CSV"
echo ""
echo "saved=$OUT_DIR/summary.csv"
echo "latest=$LATEST_CSV"
echo "live parity universe matrix done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
rm -f "$TMP_CSV"
