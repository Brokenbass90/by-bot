#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

mkdir -p logs/research runtime/local_runs

start_if_missing() {
  local name="$1"
  local pattern="$2"
  local logfile="$3"
  shift 3

  if pgrep -fal "$pattern" >/dev/null 2>&1; then
    echo "[skip] $name already running"
    return 0
  fi

  echo "[start] $name"
  nohup "$@" >> "$logfile" 2>&1 < /dev/null &
  local pid=$!
  echo "$pid" > "runtime/local_runs/${name}.pid"
  echo "[pid] $name -> $pid"
}

start_if_missing \
  "breakdown_v1_current90_focus" \
  "run_strategy_autoresearch.py --spec configs/autoresearch/breakdown_v1_current90_focus_v1.json" \
  "logs/research/local_breakdown_v1_current90_focus_20260421.log" \
  "$PYTHON_BIN" scripts/run_strategy_autoresearch.py --spec configs/autoresearch/breakdown_v1_current90_focus_v1.json

start_if_missing \
  "inplay_breakout_retest_focus" \
  "run_strategy_autoresearch.py --spec configs/autoresearch/inplay_breakout_retest_focus_v1.json" \
  "logs/research/local_inplay_breakout_retest_focus_20260421.log" \
  "$PYTHON_BIN" scripts/run_strategy_autoresearch.py --spec configs/autoresearch/inplay_breakout_retest_focus_v1.json

start_if_missing \
  "midterm_v3_backtest" \
  "scripts/run_midterm_v3_backtest.sh" \
  "logs/research/local_midterm_v3_backtest_20260421.log" \
  bash scripts/run_midterm_v3_backtest.sh

echo "[done] local rehab batch launch attempted"
