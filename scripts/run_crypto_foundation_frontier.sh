#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_BIN="$ROOT_DIR/.venv/bin/python3"
if [[ ! -x "$PY_BIN" ]]; then
  PY_BIN="$(command -v python3)"
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT_DIR/logs/research"
RUN_DIR="$ROOT_DIR/runtime/research_queue"
mkdir -p "$LOG_DIR" "$RUN_DIR"

SPECS=(
  "configs/autoresearch/core3_range_additivity_recent180_v2.json"
  "configs/autoresearch/core3_range_additivity_annual_v1.json"
  "configs/autoresearch/range_scalp_v1_annual_repair_v1.json"
  "configs/autoresearch/support_bounce_v1_regime_gap_repair_v1.json"
  "configs/autoresearch/impulse_volume_breakout_v1_annual_repair_v1.json"
)

MANIFEST="$RUN_DIR/crypto_foundation_frontier_${STAMP}.txt"
{
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "root=$ROOT_DIR"
} > "$MANIFEST"

echo "Launching crypto foundation frontier..."
for spec in "${SPECS[@]}"; do
  name="$(basename "$spec" .json)"
  log_path="$LOG_DIR/${name}_${STAMP}.log"
  nohup "$PY_BIN" "$ROOT_DIR/scripts/run_strategy_autoresearch.py" --spec "$ROOT_DIR/$spec" >"$log_path" 2>&1 &
  pid="$!"
  echo "$name pid=$pid log=$log_path" | tee -a "$MANIFEST"
done

echo "Manifest: $MANIFEST"
