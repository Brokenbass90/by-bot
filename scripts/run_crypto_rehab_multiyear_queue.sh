#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
QUEUE_PY="$ROOT/scripts/run_crypto_rehab_multiyear_queue.py"
CONFIG="${CONFIG:-$ROOT/configs/crypto_rehab_multiyear_queue.json}"
LOG_DIR="$ROOT/logs/research"
LOG_FILE="$LOG_DIR/crypto_rehab_multiyear_queue.log"
PID_FILE="$ROOT/runtime/research_queue/crypto_rehab_multiyear_queue.pid"
PROGRESS_FILE="$ROOT/runtime/research_queue/crypto_rehab_multiyear_queue_v1_progress.json"
MODE="${1:-start}"

mkdir -p "$LOG_DIR" "$(dirname "$PID_FILE")"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

case "$MODE" in
  start)
    if is_running; then
      echo "[queue] already running pid=$(cat "$PID_FILE")"
      exit 0
    fi
    nohup "$PY" "$QUEUE_PY" --config "$CONFIG" --quiet >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "[queue] started pid=$! log=$LOG_FILE"
    ;;
  status)
    if is_running; then
      echo "[queue] running pid=$(cat "$PID_FILE")"
    else
      echo "[queue] not running"
    fi
    if [[ -f "$PROGRESS_FILE" ]]; then
      echo "[queue] progress=$PROGRESS_FILE"
      tail -n 20 "$PROGRESS_FILE" || true
    fi
    ;;
  stop)
    if is_running; then
      pid="$(cat "$PID_FILE")"
      kill "$pid" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "[queue] stopped pid=$pid"
    else
      echo "[queue] not running"
    fi
    ;;
  *)
    echo "Usage: $0 [start|status|stop]" >&2
    exit 2
    ;;
esac
