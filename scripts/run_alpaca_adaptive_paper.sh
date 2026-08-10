#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

set -a
source "${ALPACA_BASE_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
source "${ALPACA_PROTECTION_ENV:-$ROOT/configs/alpaca_v38_hybrid_top4_candidate.env}"
set +a

# Paper execution receipts remain authoritative in runtime/logs, but routine
# PAPER HOLD/dry-run messages are operator noise.  Keep Telegram opt-in for
# paper only; this does not affect the separate live-account reporting path.
if [[ "${ALPACA_PAPER_TG_REPORTS:-0}" != "1" ]]; then
  unset TG_TOKEN TG_CHAT_ID TG_CHAT
fi

source .venv/bin/activate
exec python scripts/alpaca_adaptive_paper.py "$@"
