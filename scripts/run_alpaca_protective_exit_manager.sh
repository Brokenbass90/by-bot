#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

set -a
# shellcheck disable=SC1091
source configs/alpaca_live_v38.env
# shellcheck disable=SC1091
source configs/alpaca_live_v38_safe_hold.env
if [[ -f configs/alpaca_protective_exit.env ]]; then
  # shellcheck disable=SC1091
  source configs/alpaca_protective_exit.env
fi
set +a

exec .venv/bin/python scripts/alpaca_protective_exit_manager.py "$@"
