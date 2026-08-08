#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs runtime/xsec_v3_shadow
source scripts/research_loop_lock.sh
acquire_research_loop_lock "runtime/xsec_v3_shadow_loop.lock" || exit 0

while true; do
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/xsec_shadow_cycle.py \
    >> "logs/xsec_v3_shadow_${stamp}.log" 2>&1 || true
  sleep "${XSEC_SHADOW_POLL_SEC:-3600}"
done
