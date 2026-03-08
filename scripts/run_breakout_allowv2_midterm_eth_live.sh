#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

mkdir -p runtime/mplconfig
export MPLCONFIGDIR="${MPLCONFIGDIR:-$PWD/runtime/mplconfig}"

set -a
source configs/breakout_allowv2_midterm_eth_tiny.env
set +a

python3 smart_pump_reversal_bot.py
