#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

stamp="$(date -u +%Y%m%d_%H%M%S)"
research_cache="runtime/equities_1h_parity_20260710"
log="logs/alpaca_v38_fresh_cache_forward_${stamp}.log"
mkdir -p "$research_cache" logs

tickers="AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM,CRM,COIN,SHOP,XYZ,SNOW,NET,DDOG,MDB,ABNB,GS,V,MA,BAC,CVX,CAT,GE,LMT,UNH,LLY,ABBV,JNJ,MRK,COST,WMT,HD,NKE,SBUX,TSM,QCOM,TXN,NOW,INTU,ADSK,WFC,SCHW,REGN,ISRG,PG,KO,SPY,QQQ"

echo "[alpaca-v38-fresh] started ${stamp} UTC; isolated cache, research-only, no broker calls" | tee -a "$log"
EQ_TICKERS="$tickers" \
EQ_YF_PERIOD=730d \
EQ_YF_INTERVAL=60m \
EQ_DATA_DIR="$research_cache" \
bash scripts/run_equities_fetch_yf.sh 2>&1 | tee -a "$log"

set -a
source configs/alpaca_v38_hybrid_top4_candidate.env
set +a

run_case() {
  local start_month="$1"
  local end_month="$2"
  local label="$3"

  echo "[alpaca-v38-fresh] case=${label} top_n=4 months=${start_month}..${end_month}" | tee -a "$log"
  EQ_V36_RESEARCH_ONLY=1 \
  EQ_V36_DATA_DIR="$research_cache" \
  EQ_V36_SIM_TOP_N=4 \
  EQ_V36_SIM_START_MONTH="$start_month" \
  EQ_V36_SIM_END_MONTH="$end_month" \
  EQ_V36_TAG="alpaca_v38_fresh_${label}_${stamp}" \
  bash scripts/run_equities_monthly_v36_refresh.sh 2>&1 | tee -a "$log"
}

# Current-data replay is a freshness check, not a new untouched OOS because
# most of this period overlaps the original strategy-selection window.
run_case 2024-07 2026-06 current_24m_top4

# Frozen two-month pulse after the documented 2026-04 selection cutoff.  It is
# genuinely forward but too short to justify promotion by itself.
run_case 2026-05 2026-06 frozen_forward_may_jun

echo "[alpaca-v38-fresh] finished $(date -u +%Y%m%d_%H%M%S) UTC" | tee -a "$log"
