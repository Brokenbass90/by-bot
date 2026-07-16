#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${1:-$ROOT/runtime/research/public_cashcarry_station_v1_20260716_public1}"
SCREEN_NAME="${2:-cashcarry_public_v1_20260716}"

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

mkdir -p "$RUN_ROOT"
screen -dmS "$SCREEN_NAME" /bin/bash "$ROOT/scripts/supervise_public_cashcarry_station_v1.sh" "$RUN_ROOT"
echo "started research-only screen=$SCREEN_NAME run_root=$RUN_ROOT"
