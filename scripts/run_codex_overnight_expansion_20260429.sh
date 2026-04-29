#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python3}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT/logs/codex_overnight_expansion_${STAMP}"
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

echo "Codex overnight expansion started: $STAMP"
echo "LOG_DIR=$LOG_DIR"
echo "MAX_PARALLEL=$MAX_PARALLEL NICE_LEVEL=$NICE_LEVEL"

# Portfolio expansion candidates for canary v3.
launch_autoresearch "configs/autoresearch/asb1_canary_v2_bull_swap_v1.json"
launch_autoresearch "configs/autoresearch/impulse_volume_breakout_v1_annual_repair_v1.json"
launch_autoresearch "configs/autoresearch/support_bounce_v1_bull_sweep_v1.json"
launch_autoresearch "configs/autoresearch/inplay_breakout_retest_focus_v1.json"

# Geometry/level strategies: horizontal vs sloped and long/short split.
launch_autoresearch "configs/autoresearch/trendline_break_retest_v4_long_only_v1.json"
launch_autoresearch "configs/autoresearch/trendline_break_retest_v4_short_only_v1.json"
launch_autoresearch "configs/autoresearch/sloped_break_retest_v1_probe.json"
launch_autoresearch "configs/autoresearch/sloped_resistance_choch_v1_probe.json"

# Mean reversion and Elder repair/filter candidates.
launch_autoresearch "configs/autoresearch/vwap_mean_reversion_v1_sweep_v1.json"
launch_autoresearch "configs/autoresearch/elder_ts_v3_macro_relax_v1.json"
launch_autoresearch "configs/autoresearch/triple_screen_elder_v21_trend_retest_repair.json"
launch_autoresearch "configs/autoresearch/triple_screen_elder_friend_v12_focus.json"

# Breakdown overfit check: same winner params, longer standalone window.
launch_command "breakdown_v1_330d_standalone_overfit_check" env \
  BREAKDOWN_LOOKBACK_H=36 \
  BREAKDOWN_RR=1.6 \
  BREAKDOWN_SL_ATR=2.2 \
  BREAKDOWN_RSI_MAX=55 \
  BREAKDOWN_MIN_BREAK_ATR=0.2 \
  BREAKDOWN_ALLOW_LONGS=0 \
  BREAKDOWN_ALLOW_SHORTS=1 \
  "$PYTHON_BIN" backtest/run_portfolio.py \
    --strategies alt_inplay_breakdown_v1 \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT \
    --days 330 \
    --end 2026-04-25 \
    --starting_equity 100 \
    --risk_pct 0.01 \
    --leverage 1 \
    --max_positions 3 \
    --fee_bps 6 \
    --slippage_bps 2 \
    --tag claude_breakdown_330d_overfit_check_20260429

# Alpaca active lane evidence, kept low priority.
launch_command "alpaca_intraday_dynamic_v3_shadow_annual_segments" bash scripts/run_equities_intraday_dynamic_v3_shadow_annual_segments.sh

echo "All jobs launched or queued. Waiting for completion..."
wait

echo "All overnight jobs finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Logs: $LOG_DIR"
echo "Manifest: $MANIFEST"
