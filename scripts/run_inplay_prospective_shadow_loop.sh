#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" && " $* " == *" --print-config "* ]]; then
  PYTHON_BIN="$(command -v python3)"
fi
exec "$PYTHON_BIN" scripts/run_inplay_prospective_shadow_loop.py "$@"
