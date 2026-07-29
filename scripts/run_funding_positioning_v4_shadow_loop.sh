#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${ROOT}/.venv/bin/python"
RUN_HOURS="${FUNDING_V4_SHADOW_RUN_HOURS:-72}"
POLL_SEC="${FUNDING_V4_SHADOW_POLL_SEC:-300}"
END_TS=$(( $(date +%s) + RUN_HOURS * 3600 ))
LOCK_DIR="${ROOT}/runtime/funding_positioning_v4_shadow_loop.lock"
LOG="${ROOT}/logs/funding_positioning_v4_shadow.log"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "funding positioning V4 shadow already running: ${LOCK_DIR}"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT
mkdir -p "${ROOT}/logs" "${ROOT}/runtime"

while [ "$(date +%s)" -lt "${END_TS}" ]; do
  (
    cd "${ROOT}"
    "${PYTHON_BIN}" scripts/funding_positioning_v4_shadow.py
  ) >>"${LOG}" 2>&1 || true
  sleep "${POLL_SEC}"
done
