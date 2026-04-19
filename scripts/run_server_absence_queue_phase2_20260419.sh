#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p logs/research

wait_for_phase1() {
  while pgrep -f "run_server_absence_queue_20260419.sh|elder_ts_v3_macro_relax_v1|run_equities_monthly_v36_refresh.sh" >/dev/null 2>&1; do
    echo "[absence-queue-phase2] waiting for phase1 to finish..."
    sleep 60
  done
}

run_breakdown_v1_wf22() {
  echo "[absence-queue-phase2] breakdown_v1 wf22 start utc=$(date -u +%FT%TZ)"
  source .venv/bin/activate
  BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT \
  BREAKDOWN_LOOKBACK_H=36 \
  BREAKDOWN_MIN_BREAK_ATR=0.15 \
  BREAKDOWN_RSI_MAX=50 \
  BREAKDOWN_SL_ATR=1.4 \
  BREAKDOWN_RR=2.0 \
  BREAKDOWN_ALLOW_SHORTS=1 \
  BREAKDOWN_ALLOW_LONGS=0 \
  python3 scripts/run_crypto_core_walkforward.py \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT \
    --strategies alt_inplay_breakdown_v1 \
    --end 2026-04-18 \
    --total_days 330 --window_days 15 --step_days 15 \
    --min_pf 1.20 --min_net 0.0 --max_dd 25.0 \
    --tag breakdown_v1_wf22_best \
    >> logs/research/breakdown_v1_wf22_best_20260419.log 2>&1
  echo "[absence-queue-phase2] breakdown_v1 wf22 done utc=$(date -u +%FT%TZ)"
}

run_inplay_breakout_probe() {
  echo "[absence-queue-phase2] inplay_breakout probe start utc=$(date -u +%FT%TZ)"
  BREAKOUT_REGIME_MODE=any \
  BREAKOUT_SL_HTF_MULT=1.0 \
  BREAKOUT_MAX_DIST_HTF_MULT=1.5 \
  BREAKOUT_RR=3.0 \
  BREAKOUT_ALLOW_LONGS=1 \
  BREAKOUT_ALLOW_SHORTS=0 \
  BACKTEST_CACHE_ONLY=0 \
  python3 backtest/run_portfolio.py \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
    --strategies inplay_breakout \
    --days 365 --end 2025-12-31 \
    --tag breakout_htf_sl_probe_2025 \
    --starting_equity 100 --risk_pct 0.01 --leverage 1 \
    --fee_bps 6 --slippage_bps 2 \
    >> logs/research/inplay_breakout_probe_20260419.log 2>&1
  echo "[absence-queue-phase2] inplay_breakout probe done utc=$(date -u +%FT%TZ)"
}

echo "[absence-queue-phase2] start utc=$(date -u +%FT%TZ)"
wait_for_phase1
run_breakdown_v1_wf22
run_inplay_breakout_probe
echo "[absence-queue-phase2] done utc=$(date -u +%FT%TZ)"
