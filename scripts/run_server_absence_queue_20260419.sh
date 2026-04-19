#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p logs/research

wait_for_rehab_batch() {
  while pgrep -f "run_targeted_crypto_rehab_batch.sh|hzbo1_live_bridge_v1_nocache|breakout_live_bridge_v8_nocache" >/dev/null 2>&1; do
    echo "[absence-queue] waiting for targeted rehab batch to finish..."
    sleep 60
  done
}

run_elder_v3_sweep() {
  echo "[absence-queue] elder v3 sweep start utc=$(date -u +%FT%TZ)"
  source .venv/bin/activate
  python3 scripts/run_dynamic_crypto_walkforward.py \
    --config configs/autoresearch/elder_ts_v3_macro_relax_v1.json \
    >> logs/research/elder_v3_sweep_20260419.log 2>&1
  echo "[absence-queue] elder v3 sweep done utc=$(date -u +%FT%TZ)"
}

run_alpaca_v37_refresh() {
  echo "[absence-queue] alpaca v37 refresh start utc=$(date -u +%FT%TZ)"
  EQ_TICKERS="TSM,QCOM,TXN,NOW,INTU,ADSK,WFC,SCHW,REGN,ISRG,PG,KO,SPY,QQQ" \
  EQ_YF_PERIOD="730d" \
  EQ_YF_INTERVAL="60m" \
  EQ_DATA_DIR="data_cache/equities_1h" \
    bash scripts/run_equities_fetch_yf.sh >> logs/research/alpaca_v37_fetch_20260419.log 2>&1

  EQ_TICKERS="AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM,CRM,COIN,SHOP,SQ,SNOW,NET,DDOG,MDB,ABNB,GS,V,MA,BAC,CVX,CAT,GE,LMT,UNH,LLY,ABBV,JNJ,MRK,COST,WMT,HD,NKE,SBUX,TSM,QCOM,TXN,NOW,INTU,ADSK,WFC,SCHW,REGN,ISRG,PG,KO" \
  EQ_EARNINGS_LIMIT="24" \
  EQ_EARNINGS_OUT_CSV="data_cache/equities/earnings_dates.csv" \
    bash scripts/run_equities_fetch_earnings_yf.sh >> logs/research/alpaca_v37_earnings_20260419.log 2>&1

  bash scripts/run_equities_monthly_v36_refresh.sh >> logs/research/alpaca_v37_refresh_20260419.log 2>&1
  echo "[absence-queue] alpaca v37 refresh done utc=$(date -u +%FT%TZ)"
}

echo "[absence-queue] start utc=$(date -u +%FT%TZ)"
wait_for_rehab_batch
run_elder_v3_sweep
run_alpaca_v37_refresh
echo "[absence-queue] done utc=$(date -u +%FT%TZ)"
