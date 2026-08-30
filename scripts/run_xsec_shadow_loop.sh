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
  LOCK_DIR="$RUNTIME_DIR/loop.lock"
  LOG_DIR="$RUNTIME_DIR/logs"
  CANONICAL=1
else
  RUNTIME_DIR="$ROOT/runtime/xsec_v3_shadow"
  LOCK_DIR="$ROOT/runtime/xsec_v3_shadow_loop.lock"
  LOG_DIR="$ROOT/logs"
  CANONICAL=0
fi

CONFIG_CMD=(python3 scripts/research_loop_runtime_config.py --runtime-dir "$RUNTIME_DIR")
for path in "$RUNTIME_DIR/universe.json" "$RUNTIME_DIR/state.json" "$RUNTIME_DIR/decision_latest.json" "$RUNTIME_DIR/ledger.jsonl" "$LOCK_DIR" "$LOG_DIR"; do
  CONFIG_CMD+=(--write-path "$path")
done
if [[ "$PRINT_CONFIG" = "1" ]]; then
  exec "${CONFIG_CMD[@]}"
fi
if [[ "$CANONICAL" = "1" ]]; then
  "${CONFIG_CMD[@]}" --validate-env >/dev/null
fi

mkdir -p "$LOG_DIR" "$RUNTIME_DIR"
source scripts/research_loop_lock.sh
acquire_research_loop_lock "$LOCK_DIR" || exit 0

while true; do
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/xsec_shadow_cycle.py \
    --runtime-dir "$RUNTIME_DIR" \
    >> "$LOG_DIR/xsec_v3_shadow_${stamp}.log" 2>&1 || true
  sleep "${XSEC_SHADOW_POLL_SEC:-3600}"
done
