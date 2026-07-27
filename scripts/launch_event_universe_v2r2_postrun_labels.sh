#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${1:-$ROOT/runtime/research/event_universe_v2r2_20260721_public1}"
SCREEN_NAME="${2:-event_v2r2_postrun_labels_20260727}"
COLLECTOR_SCREEN="${3:-event_universe_v2r2_20260721}"

case "$SCREEN_NAME" in
  *[!A-Za-z0-9_.-]*)
    echo "invalid screen name" >&2
    exit 2
    ;;
esac

if screen -ls 2>/dev/null | grep -Fq ".${SCREEN_NAME}"; then
  echo "screen already exists: ${SCREEN_NAME}" >&2
  exit 2
fi

screen -dmS "$SCREEN_NAME" /bin/bash \
  "$ROOT/scripts/supervise_event_universe_v2r2_postrun_labels.sh" \
  "$RUN_ROOT" "$COLLECTOR_SCREEN"
echo "started research-only postrun label gate screen=${SCREEN_NAME}"
