#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY=".venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

PAIRS="${FX_CFD_PAIRS:-EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,XAUUSD}"
DAYS="${FX_CFD_DAYS:-730}"
END_DATE="${FX_CFD_END_DATE:-2026-07-06}"
LOG_DIR="${FX_CFD_LOG_DIR:-logs/fx_cfd_backfill_gate_20260706}"
mkdir -p "$LOG_DIR"

run_step() {
  local name="$1"
  shift
  local log="$LOG_DIR/${name}.log"
  {
    echo "=== $name start $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
    echo "cmd=$*"
    "$@"
    local rc=$?
    echo "=== $name finish rc=$rc $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
    return "$rc"
  } 2>&1 | tee "$log"
}

run_step "01_dukascopy_backfill_${DAYS}d" \
  env \
    FX_PAIRS="$PAIRS" \
    FX_DUKA_DAYS="$DAYS" \
    FX_DUKA_SLEEP_SEC="${FX_DUKA_SLEEP_SEC:-0.02}" \
    FX_DUKA_TIMEOUT_SEC="${FX_DUKA_TIMEOUT_SEC:-15}" \
    FX_DUKA_RETRIES="${FX_DUKA_RETRIES:-1}" \
    bash scripts/run_forex_fetch_dukascopy.sh

run_step "02_forex_data_check" \
  env \
    FX_PAIRS="$PAIRS" \
    FX_DATA_STATUS_OUT="reports/research/fx_cfd_data_status_20260706.csv" \
    bash scripts/run_forex_data_check.sh

run_step "03_cache_preflight" \
  "$PY" scripts/preflight_cache_coverage.py \
    --asset-class forex \
    --cache-dir data_cache/forex \
    --symbols "$PAIRS" \
    --days "$DAYS" \
    --end "$END_DATE" \
    --interval-min 5 \
    --min-coverage 0.60 \
    --out reports/research/preflight_fx_cfd_${DAYS}d_20260706.csv

run_step "04_fx_cfd_multi_strategy_gate" \
  "$PY" scripts/run_forex_multi_strategy_gate.py \
    --pairs "$PAIRS" \
    --strategies failure_reclaim_session_v1,liquidity_sweep_bounce_session_v1,asia_range_reversion_session_v1,range_bounce_session_v1,grid_reversion_session_v1,breakout_continuation_session_v1,trend_retest_session_v2 \
    --data-dir data_cache/forex \
    --session-start-utc 6 \
    --session-end-utc 20 \
    --stress-spread-mult 1.5 \
    --stress-swap-mult 1.5 \
    --recent-days 28 \
    --min-base-net -999999 \
    --min-stress-net -999999 \
    --min-base-return-pct-est -999999 \
    --min-stress-return-pct-est -999999 \
    --min-stress-return-pct-est-month -999999 \
    --min-trades 12 \
    --max-stress-dd 600 \
    --min-recent-stress-net -999999 \
    --min-recent-trades 1 \
    --top-n 36 \
    --risk-pct 0.25 \
    --tag fx_cfd_backfill_gate_20260706

run_step "05_fx_native_range_sweep" \
  "$PY" scripts/run_fx_native_harness.py \
    --data-dir data_cache/forex \
    --pairs "$PAIRS" \
    --setups round_level_sweep,session_range_fade,session_breakout_retest,trend_pullback \
    --outdir reports/research/fx_native_range_sweep_20260706 \
    --tp-rr 1.5,2.0,2.5 \
    --sl-atr 0.8,1.0,1.3 \
    --max-hold 120,240 \
    --fee-bps 1 \
    --slippage-bps 0.5 \
    --interval-min 60 \
    --min-coverage 0.98 \
    --max-gap-bars 12 \
    --max-fee-r 0.35

echo "fx_cfd_backfill_and_gate_20260706 done $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee "$LOG_DIR/DONE.txt"
