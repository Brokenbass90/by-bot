#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY}"
DATA_DIR="${FX_DATA_DIR:-data_cache/forex}"
YF_PERIOD="${FX_YF_PERIOD:-60d}"
YF_INTERVAL="${FX_YF_INTERVAL:-5m}"
SESSION_START="${FX_SESSION_START_UTC:-6}"
SESSION_END="${FX_SESSION_END_UTC:-20}"

MIN_BASE_NET="${FX_MIN_BASE_NET:-0}"
MIN_STRESS_NET="${FX_MIN_STRESS_NET:-0}"
MIN_TRADES="${FX_MIN_TRADES:-40}"
MAX_STRESS_DD="${FX_MAX_STRESS_DD:-300}"
RECENT_DAYS="${FX_RECENT_DAYS:-28}"
MIN_RECENT_BASE_NET="${FX_MIN_RECENT_BASE_NET:-0}"
MIN_RECENT_STRESS_NET="${FX_MIN_RECENT_STRESS_NET:-0}"
MIN_RECENT_TRADES="${FX_MIN_RECENT_TRADES:-8}"
TOP_N="${FX_TOP_N:-6}"
TAG="${FX_GATE_TAG:-fx_gate_dynamic}"

echo "forex dynamic gate start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS}"
echo "data_dir=${DATA_DIR}"
echo "session_utc=[${SESSION_START},${SESSION_END})"
echo "yf period=${YF_PERIOD} interval=${YF_INTERVAL}"
echo "gate: min_base=${MIN_BASE_NET} min_stress=${MIN_STRESS_NET} min_trades=${MIN_TRADES} max_dd=${MAX_STRESS_DD}"
echo "recent: days=${RECENT_DAYS} min_base=${MIN_RECENT_BASE_NET} min_stress=${MIN_RECENT_STRESS_NET} min_trades=${MIN_RECENT_TRADES}"

if FX_PAIRS="${PAIRS}" FX_YF_PERIOD="${YF_PERIOD}" FX_YF_INTERVAL="${YF_INTERVAL}" FX_DATA_DIR="${DATA_DIR}" \
  bash scripts/run_forex_fetch_yf.sh; then
  echo "fetch: ok"
else
  echo "fetch: warning (using existing cached CSV if available)"
fi

FX_PAIRS="${PAIRS}" FX_DATA_DIR="${DATA_DIR}" bash scripts/run_forex_data_check.sh

gate_log="$(mktemp -t fx_gate.XXXXXX.log)"
python3 scripts/run_forex_universe_gate.py \
  --pairs "${PAIRS}" \
  --presets "${FX_PRESETS:-conservative}" \
  --data-dir "${DATA_DIR}" \
  --session-start-utc "${SESSION_START}" \
  --session-end-utc "${SESSION_END}" \
  --min-base-net "${MIN_BASE_NET}" \
  --min-stress-net "${MIN_STRESS_NET}" \
  --min-trades "${MIN_TRADES}" \
  --max-stress-dd "${MAX_STRESS_DD}" \
  --recent-days "${RECENT_DAYS}" \
  --min-recent-base-net "${MIN_RECENT_BASE_NET}" \
  --min-recent-stress-net "${MIN_RECENT_STRESS_NET}" \
  --min-recent-trades "${MIN_RECENT_TRADES}" \
  --top-n "${TOP_N}" \
  --tag "${TAG}" | tee "${gate_log}"

selected_txt="$(grep -E '^selected_pairs_txt=' "${gate_log}" | tail -n 1 | cut -d= -f2-)"
selected_csv="$(grep -E '^selected=' "${gate_log}" | tail -n 1 | cut -d= -f2-)"
gated_csv="$(grep -E '^gated=' "${gate_log}" | tail -n 1 | cut -d= -f2-)"
raw_csv="$(grep -E '^raw=' "${gate_log}" | tail -n 1 | cut -d= -f2-)"

if [[ -n "${selected_txt}" && -f "${selected_txt}" ]]; then
  cp "${selected_txt}" docs/forex_selected_pairs_latest.txt
  echo "saved docs/forex_selected_pairs_latest.txt"
fi
if [[ -n "${selected_csv}" && -f "${selected_csv}" ]]; then
  cp "${selected_csv}" docs/forex_selected_pairs_latest.csv
  echo "saved docs/forex_selected_pairs_latest.csv"
fi
if [[ -n "${gated_csv}" && -f "${gated_csv}" ]]; then
  cp "${gated_csv}" docs/forex_gate_latest.csv
  echo "saved docs/forex_gate_latest.csv"
fi
if [[ -n "${raw_csv}" && -f "${raw_csv}" ]]; then
  cp "${raw_csv}" docs/forex_gate_raw_latest.csv
  echo "saved docs/forex_gate_raw_latest.csv"
fi

echo "forex dynamic gate done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
