#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p logs
set -a
source configs/alpaca_v38_hybrid_top4_candidate.env
set +a

stamp="$(date -u +%Y%m%d_%H%M%S)"
log="logs/alpaca_v38_parity_replay_${stamp}.log"

run_case() {
  local top_n="$1"
  local start_month="$2"
  local end_month="$3"
  local label="$4"

  echo "[alpaca-v38-parity] case=${label} top_n=${top_n} months=${start_month}..${end_month}" | tee -a "$log"
  EQ_V36_RESEARCH_ONLY=1 \
  EQ_V36_SIM_TOP_N="$top_n" \
  EQ_V36_SIM_START_MONTH="$start_month" \
  EQ_V36_SIM_END_MONTH="$end_month" \
  EQ_V36_TAG="alpaca_v38_parity_${label}_${stamp}" \
  bash scripts/run_equities_monthly_v36_refresh.sh 2>&1 | tee -a "$log"
}

echo "[alpaca-v38-parity] started ${stamp} UTC; cache-only, research-only, no broker calls" | tee -a "$log"

# A/B the current refresh runner's former hard-coded three-name simulation
# against the four-position cardinality advertised by the live v38 config.
run_case 3 2024-05 2026-04 current_runner_top3_control
run_case 4 2024-05 2026-04 live_cardinality_top4

# The frozen settings were selected through 2026-04.  May-June 2026 are the
# only locally cached forward months not included in that selection window.
# This is a small forward pulse, not enough by itself for promotion.
run_case 4 2026-05 2026-06 frozen_top4_forward_may_jun

echo "[alpaca-v38-parity] finished $(date -u +%Y%m%d_%H%M%S) UTC" | tee -a "$log"
