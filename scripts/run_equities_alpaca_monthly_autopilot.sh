#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL_ENV="${ALPACA_AUTOPILOT_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
OVERRIDE_ALPACA_SEND_ORDERS="${ALPACA_SEND_ORDERS-}"
OVERRIDE_ALPACA_CLOSE_STALE_POSITIONS="${ALPACA_CLOSE_STALE_POSITIONS-}"
OVERRIDE_ALPACA_AUTOPILOT_REFRESH="${ALPACA_AUTOPILOT_REFRESH-}"
OVERRIDE_ALPACA_AUTOPILOT_REFRESH_SCRIPT="${ALPACA_AUTOPILOT_REFRESH_SCRIPT-}"
OVERRIDE_ALPACA_AUTOPILOT_RUNTIME_DIR="${ALPACA_AUTOPILOT_RUNTIME_DIR-}"
OVERRIDE_ALPACA_PICKS_CSV="${ALPACA_PICKS_CSV-}"
if [[ -f "$LOCAL_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$LOCAL_ENV"
  set +a
fi

if [[ -n "${OVERRIDE_ALPACA_SEND_ORDERS:-}" ]]; then
  export ALPACA_SEND_ORDERS="$OVERRIDE_ALPACA_SEND_ORDERS"
fi
if [[ -n "${OVERRIDE_ALPACA_CLOSE_STALE_POSITIONS:-}" ]]; then
  export ALPACA_CLOSE_STALE_POSITIONS="$OVERRIDE_ALPACA_CLOSE_STALE_POSITIONS"
fi
if [[ -n "${OVERRIDE_ALPACA_AUTOPILOT_REFRESH:-}" ]]; then
  export ALPACA_AUTOPILOT_REFRESH="$OVERRIDE_ALPACA_AUTOPILOT_REFRESH"
fi
if [[ -n "${OVERRIDE_ALPACA_AUTOPILOT_REFRESH_SCRIPT:-}" ]]; then
  export ALPACA_AUTOPILOT_REFRESH_SCRIPT="$OVERRIDE_ALPACA_AUTOPILOT_REFRESH_SCRIPT"
fi
if [[ -n "${OVERRIDE_ALPACA_AUTOPILOT_RUNTIME_DIR:-}" ]]; then
  export ALPACA_AUTOPILOT_RUNTIME_DIR="$OVERRIDE_ALPACA_AUTOPILOT_RUNTIME_DIR"
fi
if [[ -n "${OVERRIDE_ALPACA_PICKS_CSV:-}" ]]; then
  export ALPACA_PICKS_CSV="$OVERRIDE_ALPACA_PICKS_CSV"
fi

ENV_PICKS_CSV="${ALPACA_PICKS_CSV:-}"
AUTO_REFRESH="${ALPACA_AUTOPILOT_REFRESH:-1}"
REFRESH_SCRIPT="${ALPACA_AUTOPILOT_REFRESH_SCRIPT:-scripts/run_equities_monthly_baseline_refresh.sh}"
RUNTIME_DIR="${ALPACA_AUTOPILOT_RUNTIME_DIR:-${EQ_V35_RUNTIME_DIR:-${EQ_BASELINE_RUNTIME_DIR:-runtime/equities_monthly}}}"
LATEST_ENV="$RUNTIME_DIR/latest_refresh.env"

echo "equities alpaca monthly autopilot start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "local_env=$LOCAL_ENV"
echo "auto_refresh=$AUTO_REFRESH"
echo "runtime_dir=$RUNTIME_DIR"

if [[ "$AUTO_REFRESH" == "1" ]]; then
  bash "$REFRESH_SCRIPT"
fi

if [[ -f "$LATEST_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$LATEST_ENV"
  set +a
fi

if [[ -n "${EQ_LATEST_REFRESH_UTC:-}" ]]; then
  export ALPACA_REFRESH_UTC="$EQ_LATEST_REFRESH_UTC"
fi

LATEST_PICKS="${EQ_LATEST_PICKS_CSV:-}"
if [[ -z "$LATEST_PICKS" && -f "$RUNTIME_DIR/latest_picks.csv" ]]; then
  LATEST_PICKS="$RUNTIME_DIR/latest_picks.csv"
fi
if [[ -z "$LATEST_PICKS" && -n "$ENV_PICKS_CSV" ]]; then
  LATEST_PICKS="$ENV_PICKS_CSV"
fi

if [[ -z "$LATEST_PICKS" ]]; then
  echo "error: no latest picks found; run refresh first" >&2
  exit 2
fi

echo "autopilot_picks_csv=$LATEST_PICKS"
export ALPACA_PICKS_CSV="$LATEST_PICKS"

source .venv/bin/activate
python3 scripts/equities_alpaca_paper_bridge.py "$@"
