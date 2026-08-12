#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs runtime/inplay_prospective_shadow_v1

while true; do
  .venv/bin/python scripts/collect_inplay_prospective_shadow.py \
    --allow-public-network \
    >> logs/inplay_prospective_shadow_v1.log 2>&1 || true
  sleep 900
done
