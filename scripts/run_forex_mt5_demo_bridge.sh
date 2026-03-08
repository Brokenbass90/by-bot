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
  source ".env"
  set +a
fi

LOCAL_ENV="${FOREX_MT5_LOCAL_ENV:-}"
if [[ -z "${LOCAL_ENV}" ]]; then
  if [[ -f "configs/forex_mt5_demo_local.env" ]]; then
    LOCAL_ENV="configs/forex_mt5_demo_local.env"
  else
    LOCAL_ENV="$HOME/.config/bybit-bot/forex_mt5_demo_local.env"
  fi
fi
if [[ -f "${LOCAL_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${LOCAL_ENV}"
  set +a
fi

cmd=(
  python3
  scripts/forex_mt5_demo_bridge.py
  --env-file "${FOREX_DEMO_ENV_FILE:-docs/forex_demo_env_latest.env}"
  --data-dir "${FOREX_DATA_DIR:-data_cache/forex}"
  --state-path "${FOREX_BRIDGE_STATE_PATH:-state/forex_mt5_demo_bridge_state.json}"
  --log-path "${FOREX_BRIDGE_LOG_PATH:-runtime/forex_mt5_demo_bridge_latest.jsonl}"
  --session-start-utc "${FOREX_SESSION_START_UTC:-6}"
  --session-end-utc "${FOREX_SESSION_END_UTC:-20}"
  --max-signal-age-bars "${FOREX_BRIDGE_MAX_SIGNAL_AGE_BARS:-1}"
  --max-bars "${FOREX_BRIDGE_MAX_BARS:-5000}"
  --max-open-per-pair "${FOREX_BRIDGE_MAX_OPEN_PER_PAIR:-1}"
  --mt5-deviation-points "${FOREX_BRIDGE_MT5_DEVIATION_POINTS:-20}"
  --mt5-magic "${FOREX_BRIDGE_MT5_MAGIC:-260308}"
)

if [[ "${FOREX_BRIDGE_SEND_ORDERS:-0}" == "1" ]]; then
  cmd+=(--send-orders)
fi

"${cmd[@]}"
