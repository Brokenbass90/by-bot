#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

LOCAL_ENV="${FUNDING_PLAN_LOCAL_ENV:-configs/funding_carry_local.env}"
if [[ -f "$LOCAL_ENV" ]]; then
  set -a
  source "$LOCAL_ENV"
  set +a
fi

python3 scripts/funding_carry_live_plan.py
