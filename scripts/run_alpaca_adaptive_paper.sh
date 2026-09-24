#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LIVE_MODE=0
for argument in "$@"; do
  case "$argument" in
    --run-intended-live|--preflight-intended-live|--prepare-intended-monthly-live) LIVE_MODE=1 ;;
  esac
done
if [[ "$LIVE_MODE" == "1" && -z "${ALPACA_BASE_LOCAL_ENV:-}" ]]; then
  echo "live_mode_requires_explicit_env" >&2
  exit 2
fi
set -a
source "${ALPACA_BASE_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
case " $* " in
  *" --run-intended "*|*" --prepare-intended "*|*" --prepare-intended-monthly "*|*" --prepare-intended-monthly-live "*|*" --run-intended-live "*|*" --preflight-intended-live "*) ;;
  *) source "${ALPACA_PROTECTION_ENV:-$ROOT/configs/alpaca_v38_hybrid_top4_candidate.env}" ;;
esac
set +a
if [[ "$LIVE_MODE" == "1" && "${ALPACA_BASE_URL:-}" != "https://api.alpaca.markets" ]]; then
  echo "live_mode_requires_exact_live_endpoint" >&2
  exit 2
fi
export ALPACA_SEND_ORDERS=0  # Driver requires an explicit --send-orders and binding.

# Paper execution receipts remain authoritative in runtime/logs, but routine
# PAPER HOLD/dry-run messages are operator noise.  Keep Telegram opt-in for
# paper only; this does not affect the separate live-account reporting path.
if [[ "${ALPACA_PAPER_TG_REPORTS:-0}" != "1" ]]; then
  unset TG_TOKEN TG_CHAT_ID TG_CHAT
fi

exec "${ALPACA_PYTHON:-$ROOT/.venv/bin/python}" scripts/alpaca_adaptive_paper.py "$@"
