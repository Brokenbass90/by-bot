#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPEC="$ROOT/configs/preregistered/event_universe_v2r2_20260721.json"
RUN_ROOT="${1:-$ROOT/runtime/research/event_universe_v2r2_20260721_public1}"
SCREEN_NAME="${2:-event_universe_v2r2_20260721}"

case "$SCREEN_NAME" in
  *[!A-Za-z0-9_.-]*)
    echo "invalid screen name" >&2
    exit 2
    ;;
esac

if ! command -v screen >/dev/null 2>&1; then
  echo "screen is required for detached launch" >&2
  exit 2
fi
if screen -ls 2>/dev/null | grep -Fq ".$SCREEN_NAME"; then
  echo "screen already exists: $SCREEN_NAME" >&2
  exit 2
fi

"$ROOT/.venv/bin/python" "$ROOT/scripts/run_event_universe_v2.py" --spec "$SPEC" status --run-root "$RUN_ROOT" >/dev/null
screen -dmS "$SCREEN_NAME" /bin/bash "$ROOT/scripts/supervise_event_universe_v2r2.sh" "$RUN_ROOT"
echo "started research-only event-universe-v2r2 screen=$SCREEN_NAME run_root=$RUN_ROOT"
