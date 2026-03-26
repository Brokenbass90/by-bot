#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL_ENV="$ROOT/configs/alpaca_paper_local.env"
if [[ -f "$LOCAL_ENV" ]]; then
  set -a
  source "$LOCAL_ENV"
  set +a
fi

source .venv/bin/activate
python3 scripts/equities_alpaca_paper_bridge.py "$@"
