#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

set -a
source "${ALPACA_BASE_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
source "${ALPACA_PROTECTION_ENV:-$ROOT/configs/alpaca_v38_hybrid_top4_candidate.env}"
set +a

source .venv/bin/activate
exec python scripts/alpaca_adaptive_paper.py "$@"
