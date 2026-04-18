#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="${ROOT}/logs/research"
mkdir -p "$LOG_DIR"

SPECS=(
  "configs/autoresearch/att1_focused_pivot_sweep_v2_nocache.json"
  "configs/autoresearch/hzbo1_live_bridge_v1_nocache.json"
  "configs/autoresearch/breakout_live_bridge_v8_nocache.json"
)

echo "[rehab-batch] start utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
for spec in "${SPECS[@]}"; do
  name="$(basename "$spec" .json)"
  log_path="${LOG_DIR}/${STAMP}_${name}.log"
  echo "[rehab-batch] running ${spec} -> ${log_path}"
  if ! nice -n 10 "$PY" scripts/run_strategy_autoresearch.py --spec "$spec" >"$log_path" 2>&1; then
    echo "[rehab-batch] WARN failed ${spec} (see ${log_path})"
  else
    echo "[rehab-batch] done ${spec}"
  fi
done
echo "[rehab-batch] finish utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
