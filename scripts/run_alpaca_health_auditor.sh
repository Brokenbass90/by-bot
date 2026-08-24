#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p runtime/alpaca_health logs
source .venv/bin/activate

python3 scripts/alpaca_health_auditor.py \
  --env-file configs/alpaca_live_v38.env \
  --manifest-json configs/alpaca_health_auditor_v1.json \
  --floor-state-json runtime/alpaca_live_v38/protective_exit_hwm.json \
  --output runtime/alpaca_health/latest.json
