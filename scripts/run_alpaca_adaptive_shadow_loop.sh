#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ARG=""
PRINT_CONFIG=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --runtime-dir) shift; RUNTIME_ARG="${1:?missing runtime directory}" ;;
    --print-config) PRINT_CONFIG=1 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$ROOT"
if [[ -n "$RUNTIME_ARG" ]]; then
  RUNTIME_DIR="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$RUNTIME_ARG")"
  CACHE_DIR="$RUNTIME_DIR/cache"
  OUT_JSON="$RUNTIME_DIR/shadow_latest.json"
  OUT_MD="$RUNTIME_DIR/shadow_latest.md"
  LEDGER="$RUNTIME_DIR/shadow_ledger.jsonl"
  LOCK_DIR="$RUNTIME_DIR/loop.lock"
  LOG_DIR="$RUNTIME_DIR/logs"
  CANONICAL=1
else
  RUNTIME_DIR="$ROOT/runtime"
  CACHE_DIR="$ROOT/runtime/equities_yf_cache"
  OUT_JSON="$ROOT/runtime/alpaca_adaptive_v1_shadow_latest.json"
  OUT_MD="$ROOT/runtime/alpaca_adaptive_v1_shadow_latest.md"
  LEDGER="$ROOT/runtime/alpaca_adaptive_v1_shadow_ledger.jsonl"
  LOCK_DIR="$ROOT/runtime/alpaca_adaptive_shadow_loop.lock"
  LOG_DIR="$ROOT/logs"
  CANONICAL=0
fi

CONFIG_CMD=(python3 scripts/research_loop_runtime_config.py --runtime-dir "$RUNTIME_DIR")
for path in "$CACHE_DIR" "$OUT_JSON" "$OUT_MD" "$LEDGER" "$LOCK_DIR" "$LOG_DIR"; do
  CONFIG_CMD+=(--write-path "$path")
done
if [[ "$PRINT_CONFIG" = "1" ]]; then
  exec "${CONFIG_CMD[@]}"
fi
if [[ "$CANONICAL" = "1" ]]; then
  "${CONFIG_CMD[@]}" --validate-env >/dev/null
fi

mkdir -p "$LOG_DIR" "$CACHE_DIR"
source scripts/research_loop_lock.sh
acquire_research_loop_lock "$LOCK_DIR" || exit 0

while true; do
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/alpaca_adaptive_shadow.py \
    --start 2025-01-01 \
    --capital "${ALPACA_ADAPTIVE_SHADOW_CAPITAL:-484}" \
    --target-alloc-pct 70 \
    --max-positions 4 \
    --preset baseline \
    --cache-dir "$CACHE_DIR" \
    --out-json "$OUT_JSON" \
    --out-md "$OUT_MD" \
    --ledger-jsonl "$LEDGER" \
    >> "$LOG_DIR/alpaca_adaptive_shadow_${stamp}.log" 2>&1 || true
  sleep "${ALPACA_ADAPTIVE_SHADOW_POLL_SEC:-21600}"
done
