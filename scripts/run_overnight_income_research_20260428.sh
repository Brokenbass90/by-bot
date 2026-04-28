#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python3}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT/logs/overnight_income_research_${STAMP}"
MANIFEST="$LOG_DIR/manifest.tsv"
MAX_PARALLEL="${OVERNIGHT_MAX_PARALLEL:-3}"
NICE_LEVEL="${OVERNIGHT_NICE_LEVEL:-15}"

mkdir -p "$LOG_DIR"
printf "kind\tname\tpid\tlog\tstarted_utc\n" > "$MANIFEST"

export BACKTEST_CACHE_ONLY="${BACKTEST_CACHE_ONLY:-1}"
export CACHE_ONLY="${CACHE_ONLY:-$BACKTEST_CACHE_ONLY}"
export PYTHONDONTWRITEBYTECODE=1

active_jobs() {
  jobs -r -p | wc -l | tr -d ' '
}

wait_for_slot() {
  while [ "$(active_jobs)" -ge "$MAX_PARALLEL" ]; do
    sleep 30
  done
}

launch_autoresearch() {
  local spec="$1"
  local name
  name="$(basename "$spec" .json)"
  local log="$LOG_DIR/${name}.log"

  if [ ! -f "$spec" ]; then
    echo "[skip] missing spec: $spec" | tee -a "$LOG_DIR/missing.log"
    return 0
  fi

  wait_for_slot
  (
    echo "== START $(date -u +%Y-%m-%dT%H:%M:%SZ) :: $spec =="
    echo "BACKTEST_CACHE_ONLY=$BACKTEST_CACHE_ONLY CACHE_ONLY=$CACHE_ONLY"
    nice -n "$NICE_LEVEL" "$PYTHON_BIN" scripts/run_strategy_autoresearch.py --spec "$spec"
    rc=$?
    echo "== END $(date -u +%Y-%m-%dT%H:%M:%SZ) :: $spec :: rc=$rc =="
    exit "$rc"
  ) > "$log" 2>&1 &
  local pid=$!
  printf "autoresearch\t%s\t%s\t%s\t%s\n" "$name" "$pid" "$log" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$MANIFEST"
  echo "[launch] autoresearch $name pid=$pid log=$log"
}

launch_command() {
  local name="$1"
  shift
  local log="$LOG_DIR/${name}.log"
  wait_for_slot
  (
    echo "== START $(date -u +%Y-%m-%dT%H:%M:%SZ) :: $name =="
    nice -n "$NICE_LEVEL" "$@"
    rc=$?
    echo "== END $(date -u +%Y-%m-%dT%H:%M:%SZ) :: $name :: rc=$rc =="
    exit "$rc"
  ) > "$log" 2>&1 &
  local pid=$!
  printf "command\t%s\t%s\t%s\t%s\n" "$name" "$pid" "$log" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$MANIFEST"
  echo "[launch] command $name pid=$pid log=$log"
}

echo "Overnight income research started: $STAMP"
echo "LOG_DIR=$LOG_DIR"
echo "MAX_PARALLEL=$MAX_PARALLEL NICE_LEVEL=$NICE_LEVEL"

if [ "${OVERNIGHT_REMAINING_ONLY:-0}" != "1" ]; then
  # Current live canary improvement and regression repair.
  launch_autoresearch "configs/autoresearch/att1_focused_pivot_sweep_v2_nocache.json"
  launch_autoresearch "configs/autoresearch/flat_live_universe_repair_v2.json"
  launch_autoresearch "configs/autoresearch/breakdown_v1_recent180_focus_v1.json"
  launch_autoresearch "configs/autoresearch/inplay_breakout_retest_focus_v1.json"
fi

# Sleeves that should become the next expansion candidates if they pass.
launch_autoresearch "configs/autoresearch/support_bounce_v1_annual_repair_v2.json"
launch_autoresearch "configs/autoresearch/ivb1_wider_universe_v1.json"
launch_autoresearch "configs/autoresearch/range_scalp_v1_annual_focus_v2.json"
launch_autoresearch "configs/autoresearch/pump_fade_v4r_bear_window.json"
launch_autoresearch "configs/autoresearch/flat_slope_symbol_baskets_v3_expand.json"

# Elder as a filter/strategy candidate: first make it tradeful, then validate.
launch_autoresearch "configs/autoresearch/elder_ts_v3_macro_relax_v1.json"

# Alpaca income lane: evaluate the intraday dynamic v3 shadow path.
launch_command "alpaca_intraday_dynamic_v3_shadow_annual_segments" bash scripts/run_equities_intraday_dynamic_v3_shadow_annual_segments.sh

echo "All jobs launched or queued. Waiting for completion..."
wait

echo "All overnight jobs finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Logs: $LOG_DIR"
echo "Manifest: $MANIFEST"
