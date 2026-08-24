#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="dryrun"
if [[ "${1:-}" == "--send-orders" ]]; then
  MODE="send_orders"
  shift
fi

set -a
source configs/alpaca_v38_hybrid_top4_candidate.env
source configs/alpaca_live_v38.env
if [[ -f configs/alpaca_protective_exit.env ]]; then
  source configs/alpaca_protective_exit.env
fi
source configs/alpaca_live_v38_safe_hold.env
set +a

if [[ "$MODE" == "dryrun" ]]; then
  export ALPACA_SEND_ORDERS=0
else
  export ALPACA_SEND_ORDERS=1
fi

mkdir -p logs
LOG_FILE="logs/alpaca_live_v38_${MODE}_$(date +%Y%m%d_%H%M%S).log"

echo "alpaca_live_v38_once mode=$MODE"
echo "base_url=$ALPACA_BASE_URL"
echo "send_orders=$ALPACA_SEND_ORDERS"
echo "capital_cap=${ALPACA_CAPITAL_OVERRIDE_USD:-}"
echo "log_file=$LOG_FILE"

source .venv/bin/activate
python3 scripts/equities_alpaca_paper_bridge.py "$@" 2>&1 | tee "$LOG_FILE"
