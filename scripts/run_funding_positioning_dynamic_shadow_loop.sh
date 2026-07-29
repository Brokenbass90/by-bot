#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
UNIVERSE="$ROOT/runtime/funding_positioning_dynamic_universe.json"
LOCK_DIR="$ROOT/runtime/funding_positioning_dynamic_shadow_loop.lock"
LOG="$ROOT/logs/funding_positioning_dynamic_shadow.log"

mkdir -p "$ROOT/runtime" "$ROOT/logs"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "funding positioning dynamic shadow already running"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

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
      --state runtime/funding_positioning_dynamic_shadow_state.json \
      --ledger runtime/funding_positioning_dynamic_shadow_ledger.jsonl \
      --summary runtime/funding_positioning_dynamic_shadow_summary.json \
      >> "$LOG" 2>&1 || true
  fi
  sleep 300
done
