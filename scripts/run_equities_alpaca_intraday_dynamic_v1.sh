#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Instance lock: prevent two simultaneous runs (cron overlap protection) ──
LOCK_FILE="${TMPDIR:-/tmp}/alpaca_intraday_bridge.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date -u +%H:%M:%SZ)] already running — skipping this tick" >&2
  exit 0
fi

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

MODE_SET=0
for arg in "$@"; do
  if [[ "$arg" == "--dry-run" || "$arg" == "--live" ]]; then
    MODE_SET=1
    break
  fi
done

if [[ "$MODE_SET" -eq 0 ]]; then
  set -- --live "$@"
fi

python3 scripts/equities_alpaca_intraday_bridge.py "$@"
