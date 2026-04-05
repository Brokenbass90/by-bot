#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_ENV="${ALPACA_BASE_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
DYNAMIC_ENV="${ALPACA_INTRADAY_DYNAMIC_ENV:-$ROOT/configs/alpaca_intraday_dynamic_v1.env}"

if [[ -f "$BASE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BASE_ENV"
  set +a
fi

if [[ -f "$DYNAMIC_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$DYNAMIC_ENV"
  set +a
fi

source .venv/bin/activate

if [[ $# -eq 0 ]]; then
  set -- --once
fi

python3 scripts/equities_alpaca_intraday_bridge.py --live "$@"
