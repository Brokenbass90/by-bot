#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

OUT_DIR="backtest_runs/forex_batch_$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"

PAIRS_CSV="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}"
SESSION_START="${FX_SESSION_START_UTC:-6}"
SESSION_END="${FX_SESSION_END_UTC:-20}"

_default_spread() {
  case "$1" in
    EURUSD) echo "1.0" ;;
    GBPUSD) echo "1.2" ;;
    USDJPY) echo "1.0" ;;
    *) echo "1.2" ;;
  esac
}

_default_swap_long() {
  case "$1" in
    EURUSD) echo "-0.3" ;;
    GBPUSD) echo "-0.4" ;;
    USDJPY) echo "-0.2" ;;
    *) echo "-0.2" ;;
  esac
}

_default_swap_short() {
  case "$1" in
    EURUSD) echo "-0.3" ;;
    GBPUSD) echo "-0.4" ;;
    USDJPY) echo "-0.2" ;;
    *) echo "-0.2" ;;
  esac
}

echo "forex pilot batch start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS_CSV}"
echo "session_utc=[${SESSION_START},${SESSION_END})"
echo "out_dir=${OUT_DIR}"

IFS=',' read -r -a PAIRS <<< "$PAIRS_CSV"
for RAW in "${PAIRS[@]}"; do
  SYM="$(echo "$RAW" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  [[ -z "$SYM" ]] && continue

  CSV_PATH="${FX_DATA_DIR:-data_cache/forex}/${SYM}_M5.csv"
  SPREAD_VAR="FX_${SYM}_SPREAD"
  SWAP_LONG_VAR="FX_${SYM}_SWAP_LONG"
  SWAP_SHORT_VAR="FX_${SYM}_SWAP_SHORT"

  SPREAD="${!SPREAD_VAR-}"
  SWAP_LONG="${!SWAP_LONG_VAR-}"
  SWAP_SHORT="${!SWAP_SHORT_VAR-}"
  [[ -z "${SPREAD}" ]] && SPREAD="$(_default_spread "$SYM")"
  [[ -z "${SWAP_LONG}" ]] && SWAP_LONG="$(_default_swap_long "$SYM")"
  [[ -z "${SWAP_SHORT}" ]] && SWAP_SHORT="$(_default_swap_short "$SYM")"

  if [[ ! -f "$CSV_PATH" ]]; then
    echo "skip ${SYM}: missing ${CSV_PATH}"
    continue
  fi

  echo ""
  echo ">>> RUN forex_${SYM}"
  python3 scripts/run_forex_backtest.py \
    --symbol "$SYM" \
    --csv "$CSV_PATH" \
    --tag "pilot_${SYM}_$(date -u +%Y%m%d_%H%M%S)" \
    --spread_pips "$SPREAD" \
    --swap_long "$SWAP_LONG" \
    --swap_short "$SWAP_SHORT" \
    --session_start_utc "$SESSION_START" \
    --session_end_utc "$SESSION_END" \
    | tee "${OUT_DIR}/${SYM}.log"
done

echo ""
echo "forex pilot batch done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "logs=${OUT_DIR}"
