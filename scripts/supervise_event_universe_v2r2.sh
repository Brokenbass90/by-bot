#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPEC="$ROOT/configs/preregistered/event_universe_v2r2_20260721.json"
RUN_ROOT="${1:-$ROOT/runtime/research/event_universe_v2r2_20260721_public1}"
MAX_PROCESS_ATTEMPTS=6
attempt=1

cd "$ROOT" || exit 2
"$ROOT/.venv/bin/python" "$ROOT/scripts/run_event_universe_v2.py" --spec "$SPEC" status --run-root "$RUN_ROOT" >/dev/null || exit 2
echo "research-only event-universe-v2r2 supervisor start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

while [ "$attempt" -le "$MAX_PROCESS_ATTEMPTS" ]; do
  args=(
    "$ROOT/.venv/bin/python"
    "$ROOT/scripts/run_event_universe_v2.py"
    --spec "$SPEC"
    run
    --run-root "$RUN_ROOT"
    --allow-public-network
    --enable-durable-collector
    --acknowledge-research-only
  )

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
  if [ "$status" -eq 3 ]; then
    echo "terminal source-finality conflict; V2r2 stops without retry" >&2
    exit 3
  fi

  attempt=$((attempt + 1))
  if [ "$attempt" -le "$MAX_PROCESS_ATTEMPTS" ]; then
    sleep 60
  fi
done

exit "$status"
