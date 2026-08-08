#!/usr/bin/env bash
# Prospective, fixed-universe, risk-zero lifecycle after the N42 audit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
UNIVERSE="$ROOT/configs/research/funding_positioning_post_n42_frozen_20260808.json"
LOCK_DIR="$ROOT/runtime/funding_positioning_post_n42_frozen_loop.lock"
LOG="$ROOT/logs/funding_positioning_post_n42_frozen.log"

mkdir -p "$ROOT/runtime" "$ROOT/logs"
source "$ROOT/scripts/research_loop_lock.sh"
acquire_research_loop_lock "$LOCK_DIR" || exit 0

while true; do
  "$PYTHON_BIN" scripts/funding_positioning_v4_shadow.py \
    --symbols-json "$UNIVERSE" \
    --state runtime/funding_positioning_post_n42_frozen_state.json \
    --ledger runtime/funding_positioning_post_n42_frozen_ledger.jsonl \
    --summary runtime/funding_positioning_post_n42_frozen_summary.json \
    >> "$LOG" 2>&1 || true
  sleep 300
done
