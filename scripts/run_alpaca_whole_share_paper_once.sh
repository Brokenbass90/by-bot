#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

set -a
source configs/alpaca_v38_active_paper_candidate.env
if [[ -f configs/alpaca_paper_local.env ]]; then
  source configs/alpaca_paper_local.env
fi
source configs/alpaca_v38_whole_share_paper_default_off.env
set +a

# Immutable launcher guardrails: the profile can evaluate plans but cannot buy.
export ALPACA_BASE_URL=https://paper-api.alpaca.markets
export ALPACA_SEND_ORDERS=0
export ALPACA_ALLOW_NEW_ENTRIES=0

mkdir -p logs
source .venv/bin/activate
python3 scripts/equities_alpaca_paper_bridge.py "$@"
