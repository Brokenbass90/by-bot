#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python3"
RUNNER="${ROOT}/scripts/run_strategy_autoresearch.py"
LOG_DIR="${ROOT}/logs/crypto_next_package_queue"
LOCK_FILE="${ROOT}/runtime/crypto_next_package_queue.lock"

mkdir -p "${LOG_DIR}" "${ROOT}/runtime"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "queue already running"
  exit 0
fi

specs=(
  "configs/autoresearch/package_mtpb_recovery_v1.json"
  "configs/autoresearch/package_pfs1_pump_fade_v1.json"
  "configs/autoresearch/package_gs1_grid_smart_v1.json"
)

wait_for_active_sweep() {
  while pgrep -f "scripts/run_strategy_autoresearch.py --spec" >/dev/null 2>&1; do
    echo "$(date -u +%FT%TZ) waiting for active autoresearch sweep"
    sleep 300
  done
}

for spec in "${specs[@]}"; do
  wait_for_active_sweep
  name="$(basename "${spec}" .json)"
  log="${LOG_DIR}/${name}_$(date -u +%Y%m%d_%H%M%S).log"
  echo "$(date -u +%FT%TZ) starting ${spec}; log=${log}"
  if nice -n 10 "${PYTHON}" "${RUNNER}" --spec "${ROOT}/${spec}" >"${log}" 2>&1; then
    echo "$(date -u +%FT%TZ) completed ${spec}"
  else
    rc=$?
    echo "$(date -u +%FT%TZ) failed ${spec}; rc=${rc}"
  fi
done

echo "$(date -u +%FT%TZ) crypto next package queue finished"
