#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

TICKERS="${EQ_V36_TICKERS:-AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM,CRM,COIN,SHOP,SQ,SNOW,NET,DDOG,MDB,ABNB,GS,V,MA,BAC,CVX,CAT,GE,LMT,UNH,LLY,ABBV,JNJ,MRK,COST,WMT,HD,NKE,SBUX}"
BENCH_TICKERS="${EQ_V36_BENCH_TICKERS:-SPY,QQQ}"
ALL_FETCH_TICKERS="${EQ_V36_FETCH_TICKERS:-${TICKERS},${BENCH_TICKERS}}"
DATA_DIR="${EQ_V36_DATA_DIR:-data_cache/equities_1h}"
EARNINGS_CSV="${EQ_V36_EARNINGS_CSV:-data_cache/equities/earnings_dates.csv}"
CLUSTER_GROUPS="${EQ_V36_CLUSTER_GROUPS:-AAPL,MSFT,GOOGL,AMZN,META;NVDA,AMD,AVGO,ADBE,CRM,ORCL;META,NFLX,ABNB;CRWD,PANW,NET,DDOG,SNOW,MDB;PLTR,UBER,SHOP,COIN,SQ;JPM,GS,BAC,V,MA;XOM,CVX;CAT,GE,LMT;UNH,LLY,ABBV,JNJ,MRK;COST,WMT,HD,NKE,SBUX}"
FORBID_PAIRS="${EQ_V36_FORBID_PAIRS:-NVDA:AMD;CRWD:PANW;META:NFLX;V:MA}"

FETCH_PERIOD="${EQ_V36_YF_PERIOD:-730d}"
FETCH_INTERVAL="${EQ_V36_YF_INTERVAL:-60m}"
EARNINGS_LIMIT="${EQ_V36_EARNINGS_LIMIT:-24}"
TAG="${EQ_V36_TAG:-equities_monthly_v36_candidate_refresh}"
RUNTIME_DIR="${EQ_V36_RUNTIME_DIR:-runtime/equities_monthly_v36}"

echo "equities monthly v36 refresh start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "tickers=${TICKERS}"
echo "bench_tickers=${BENCH_TICKERS}"
echo "data_dir=${DATA_DIR}"
echo "earnings_csv=${EARNINGS_CSV}"
echo "runtime_dir=${RUNTIME_DIR}"

EQ_TICKERS="$ALL_FETCH_TICKERS" \
EQ_YF_PERIOD="$FETCH_PERIOD" \
EQ_YF_INTERVAL="$FETCH_INTERVAL" \
EQ_DATA_DIR="$DATA_DIR" \
bash scripts/run_equities_fetch_yf.sh

EQ_TICKERS="$TICKERS" \
EQ_EARNINGS_LIMIT="$EARNINGS_LIMIT" \
EQ_EARNINGS_OUT_CSV="$EARNINGS_CSV" \
bash scripts/run_equities_fetch_earnings_yf.sh

python3 scripts/equities_monthly_research_sim.py \
  --tickers "$TICKERS" \
  --data-dir "$DATA_DIR" \
  --top-n 3 \
  --max-hold-days 16 \
  --lookback-days 28 \
  --min-mom-lookback-pct 2.5 \
  --pullback-min-pct -12.0 \
  --pullback-max-pct -1.5 \
  --regime-min-breadth-sma-pct 60 \
  --regime-min-breadth-mom-pct 45 \
  --regime-min-avg-mom-pct 1.5 \
  --earnings-csv "$EARNINGS_CSV" \
  --earnings-blackout-days-before 5 \
  --earnings-blackout-days-after 2 \
  --benchmark-tickers "$BENCH_TICKERS" \
  --benchmark-data-dir "$DATA_DIR" \
  --benchmark-lookback-days 60 \
  --benchmark-min-above-sma-count 1 \
  --corr-lookback-days 60 \
  --max-pair-corr 0.75 \
  --corr-penalty-mult 2.5 \
  --corr-penalty-threshold 0.5 \
  --universe-top-k 14 \
  --universe-score-lookback-days 80 \
  --position-weight-mode score_inv_vol \
  --cluster-groups "$CLUSTER_GROUPS" \
  --max-per-cluster 1 \
  --forbid-pairs "$FORBID_PAIRS" \
  --stop-atr-mult 1.7 \
  --target-atr-mult 4.0 \
  --intramonth-portfolio-stop-pct 0.04 \
  --tag "$TAG"

if ! python3 scripts/build_equities_monthly_live_cycle.py \
  --tickers "$TICKERS" \
  --data-dir "$DATA_DIR" \
  --top-n 3 \
  --lookback-days 28 \
  --min-mom-lookback-pct 2.5 \
  --pullback-min-pct -12.0 \
  --pullback-max-pct -1.5 \
  --benchmark-tickers "$BENCH_TICKERS" \
  --benchmark-data-dir "$DATA_DIR" \
  --benchmark-lookback-days 60 \
  --benchmark-min-above-sma-count 1 \
  --corr-lookback-days 60 \
  --max-pair-corr 0.75 \
  --corr-penalty-mult 2.5 \
  --corr-penalty-threshold 0.5 \
  --universe-top-k 14 \
  --universe-score-lookback-days 80 \
  --position-weight-mode score_inv_vol \
  --cluster-groups "$CLUSTER_GROUPS" \
  --max-per-cluster 1 \
  --stop-atr-mult 1.7 \
  --target-atr-mult 4.0 \
  --out-picks-csv "$RUNTIME_DIR/current_cycle_picks.csv" \
  --out-summary-csv "$RUNTIME_DIR/current_cycle_summary.csv"; then
  echo "warn: current-cycle builder produced no fresh picks"
  rm -f "$RUNTIME_DIR/current_cycle_picks.csv" "$RUNTIME_DIR/current_cycle_summary.csv"
fi

mkdir -p "$RUNTIME_DIR"
LATEST_RUN_DIR="$(ls -1dt backtest_runs/equities_monthly_research_*_"$TAG" 2>/dev/null | head -n 1)"
if [[ -z "${LATEST_RUN_DIR:-}" ]]; then
  echo "error: latest equities refresh run not found for tag=$TAG" >&2
  exit 1
fi

LATEST_PICKS_CSV="$LATEST_RUN_DIR/picks.csv"
LATEST_SUMMARY_CSV="$LATEST_RUN_DIR/summary.csv"
cp "$LATEST_PICKS_CSV" "$RUNTIME_DIR/latest_picks.csv"
cp "$LATEST_SUMMARY_CSV" "$RUNTIME_DIR/latest_summary.csv"

cat > "$RUNTIME_DIR/latest_refresh.env" <<EOF
EQ_LATEST_RUN_DIR=$LATEST_RUN_DIR
EQ_LATEST_PICKS_CSV=$LATEST_PICKS_CSV
EQ_LATEST_SUMMARY_CSV=$LATEST_SUMMARY_CSV
EQ_CURRENT_CYCLE_PICKS_CSV=$RUNTIME_DIR/current_cycle_picks.csv
EQ_CURRENT_CYCLE_SUMMARY_CSV=$RUNTIME_DIR/current_cycle_summary.csv
EQ_LATEST_REFRESH_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
EQ_V36_ACTIVE_TICKERS=$TICKERS
EOF

echo "latest_run_dir=$LATEST_RUN_DIR"
echo "latest_picks_csv=$LATEST_PICKS_CSV"
echo "latest_summary_csv=$LATEST_SUMMARY_CSV"
