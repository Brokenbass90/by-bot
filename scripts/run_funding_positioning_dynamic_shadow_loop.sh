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
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
if [[ -n "$RUNTIME_ARG" ]]; then
  RUNTIME_DIR="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$RUNTIME_ARG")"
  UNIVERSE="$RUNTIME_DIR/universe.json"
  STATE="$RUNTIME_DIR/state.json"
  LEDGER="$RUNTIME_DIR/ledger.jsonl"
  SUMMARY="$RUNTIME_DIR/summary.json"
  LOCK_DIR="$RUNTIME_DIR/loop.lock"
  LOG="$RUNTIME_DIR/logs/shadow.log"
  CANONICAL=1
else
  RUNTIME_DIR="$ROOT/runtime"
  UNIVERSE="$ROOT/runtime/funding_positioning_dynamic_universe.json"
  STATE="$ROOT/runtime/funding_positioning_dynamic_shadow_state.json"
  LEDGER="$ROOT/runtime/funding_positioning_dynamic_shadow_ledger.jsonl"
  SUMMARY="$ROOT/runtime/funding_positioning_dynamic_shadow_summary.json"
  LOCK_DIR="$ROOT/runtime/funding_positioning_dynamic_shadow_loop.lock"
  LOG="$ROOT/logs/funding_positioning_dynamic_shadow.log"
  CANONICAL=0
fi

CONFIG_CMD=(python3 scripts/research_loop_runtime_config.py --runtime-dir "$RUNTIME_DIR")
for path in "$UNIVERSE" "$STATE" "$LEDGER" "$SUMMARY" "$LOCK_DIR" "$LOG"; do
  CONFIG_CMD+=(--write-path "$path")
done
if [[ "$PRINT_CONFIG" = "1" ]]; then
  exec "${CONFIG_CMD[@]}"
fi
if [[ "$CANONICAL" = "1" ]]; then
  "${CONFIG_CMD[@]}" --validate-env >/dev/null
fi

mkdir -p "$(dirname "$LOG")" "$RUNTIME_DIR"
source "$ROOT/scripts/research_loop_lock.sh"
acquire_research_loop_lock "$LOCK_DIR" || exit 0

while true; do
  now="$(date +%s)"
  mtime=0
  if [[ -f "$UNIVERSE" ]]; then
    mtime="$(stat -f '%m' "$UNIVERSE" 2>/dev/null || stat -c '%Y' "$UNIVERSE" 2>/dev/null || echo 0)"
  fi
  if (( now - mtime >= 14400 )); then
    "$PYTHON_BIN" scripts/build_funding_positioning_dynamic_universe.py \
      --out "$UNIVERSE" --top-n 16 >> "$LOG" 2>&1 || true
  fi
  if [[ -f "$UNIVERSE" ]]; then
    "$PYTHON_BIN" scripts/funding_positioning_v4_shadow.py \
      --symbols-json "$UNIVERSE" \
      --state "$STATE" \
      --ledger "$LEDGER" \
      --summary "$SUMMARY" \
      >> "$LOG" 2>&1 || true
  fi
  sleep 300
done
