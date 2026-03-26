#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

mkdir -p runtime/live_health_guard

export LIVE_GUARD_LOCAL="${LIVE_GUARD_LOCAL:-1}"
export LIVE_GUARD_SINCE="${LIVE_GUARD_SINCE:-2 hours ago}"

python3 scripts/live_health_guard.py
