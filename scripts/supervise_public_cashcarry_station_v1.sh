#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${1:-$ROOT/runtime/research/public_cashcarry_station_v1_20260716_public1}"
MAX_PROCESS_ATTEMPTS=6
attempt=1

cd "$ROOT" || exit 2
mkdir -p "$RUN_ROOT"
exec >>"$RUN_ROOT/supervisor.log" 2>&1
echo "research-only supervisor start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

while [ "$attempt" -le "$MAX_PROCESS_ATTEMPTS" ]; do
  args=(
    "$ROOT/.venv/bin/python"
    "$ROOT/scripts/run_public_cashcarry_station_v1.py"
    run
    --run-root "$RUN_ROOT"
    --allow-public-network
    --enable-durable-collector
    --enable-research-shadow
    --acknowledge-research-only
  )
  if [ -f "$RUN_ROOT/station_state.json" ]; then
    args+=(--resume-existing)
  fi

  if command -v caffeinate >/dev/null 2>&1; then
    caffeinate -dimsu "${args[@]}"
    status=$?
  else
    "${args[@]}"
    status=$?
  fi
  if [ "$status" -eq 0 ]; then
    exit 0
  fi

  attempt=$((attempt + 1))
  if [ "$attempt" -le "$MAX_PROCESS_ATTEMPTS" ]; then
    sleep 60
  fi
done

exit "$status"
