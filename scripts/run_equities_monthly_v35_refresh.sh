#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

SEED_TICKERS="${EQ_V35_SEED_TICKERS:-AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM,CRM,COIN,SHOP,SQ,SNOW,NET,DDOG,MDB,ABNB,GS,V,MA,BAC,CVX,CAT,GE,LMT,UNH,LLY,ABBV,JNJ,MRK,COST,WMT,HD,NKE,SBUX}"
CORE_TICKERS="${EQ_V35_CORE_TICKERS:-AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM}"
BENCH_TICKERS="${EQ_V35_BENCH_TICKERS:-SPY,QQQ}"
ALL_FETCH_TICKERS="${EQ_V35_FETCH_TICKERS:-${SEED_TICKERS},${BENCH_TICKERS}}"
DATA_DIR="${EQ_V35_DATA_DIR:-data_cache/equities_1h}"
EARNINGS_CSV="${EQ_V35_EARNINGS_CSV:-data_cache/equities/earnings_dates.csv}"
CLUSTER_GROUPS="${EQ_V35_CLUSTER_GROUPS:-AAPL,MSFT,GOOGL,AMZN,META;NVDA,AMD,AVGO,ADBE,CRM,ORCL;META,NFLX,ABNB;CRWD,PANW,NET,DDOG,SNOW,MDB;PLTR,UBER,SHOP,COIN,SQ;JPM,GS,BAC,V,MA;XOM,CVX;CAT,GE,LMT;UNH,LLY,ABBV,JNJ,MRK;COST,WMT,HD,NKE,SBUX}"
FORBID_PAIRS="${EQ_V35_FORBID_PAIRS:-NVDA:AMD;CRWD:PANW;META:NFLX;V:MA}"

FETCH_PERIOD="${EQ_V35_YF_PERIOD:-730d}"
FETCH_INTERVAL="${EQ_V35_YF_INTERVAL:-60m}"
EARNINGS_LIMIT="${EQ_V35_EARNINGS_LIMIT:-24}"
TAG="${EQ_V35_TAG:-equities_monthly_v35_candidate_refresh}"
RUNTIME_DIR="${EQ_V35_RUNTIME_DIR:-runtime/equities_monthly_v35}"
DYNAMIC_UNIVERSE_ENABLE="${EQ_V35_DYNAMIC_UNIVERSE:-0}"
DYNAMIC_TOP_K="${EQ_V35_DYNAMIC_TOP_K:-18}"
DYNAMIC_LOOKBACK_DAYS="${EQ_V35_DYNAMIC_LOOKBACK_DAYS:-80}"
DYNAMIC_MAX_PER_CLUSTER="${EQ_V35_DYNAMIC_MAX_PER_CLUSTER:-2}"
DYNAMIC_TAG="${EQ_V35_DYNAMIC_TAG:-equities_v35_watchlist}"

echo "equities monthly v35 refresh start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "core_tickers=${CORE_TICKERS}"
echo "seed_tickers=${SEED_TICKERS}"
echo "bench_tickers=${BENCH_TICKERS}"
echo "data_dir=${DATA_DIR}"
echo "earnings_csv=${EARNINGS_CSV}"
echo "runtime_dir=${RUNTIME_DIR}"
echo "dynamic_universe=${DYNAMIC_UNIVERSE_ENABLE}"

EQ_TICKERS="$ALL_FETCH_TICKERS" \
EQ_YF_PERIOD="$FETCH_PERIOD" \
EQ_YF_INTERVAL="$FETCH_INTERVAL" \
EQ_DATA_DIR="$DATA_DIR" \
bash scripts/run_equities_fetch_yf.sh

ACTIVE_TICKERS="$CORE_TICKERS"
if [[ "$DYNAMIC_UNIVERSE_ENABLE" == "1" ]]; then
  python3 scripts/equities_universe_refresh.py \
    --tickers "$SEED_TICKERS" \
    --data-dir "$DATA_DIR" \
    --lookback-days "$DYNAMIC_LOOKBACK_DAYS" \
    --top-k "$DYNAMIC_TOP_K" \
    --cluster-groups "$CLUSTER_GROUPS" \
    --max-per-cluster "$DYNAMIC_MAX_PER_CLUSTER" \
    --tag "$DYNAMIC_TAG"

  WATCHLIST_RUN_DIR="$(ls -1dt backtest_runs/equities_universe_refresh_*_"$DYNAMIC_TAG" 2>/dev/null | head -n 1)"
  if [[ -z "${WATCHLIST_RUN_DIR:-}" ]]; then
    echo "error: dynamic watchlist run not found for tag=$DYNAMIC_TAG" >&2
    exit 1
  fi
  WATCHLIST_CSV="$WATCHLIST_RUN_DIR/watchlist.csv"
  ACTIVE_TICKERS="$(tail -n +2 "$WATCHLIST_CSV" | cut -d, -f1 | paste -sd, -)"
  if [[ -z "${ACTIVE_TICKERS:-}" ]]; then
    echo "error: dynamic watchlist resolved to empty tickers" >&2
    exit 1
  fi
  echo "dynamic_watchlist_dir=$WATCHLIST_RUN_DIR"
  echo "dynamic_watchlist_tickers=$ACTIVE_TICKERS"
fi

EQ_TICKERS="$ACTIVE_TICKERS" \
EQ_EARNINGS_LIMIT="$EARNINGS_LIMIT" \
EQ_EARNINGS_OUT_CSV="$EARNINGS_CSV" \
bash scripts/run_equities_fetch_earnings_yf.sh

python3 scripts/equities_monthly_research_sim.py \
  --tickers "$ACTIVE_TICKERS" \
  --data-dir "$DATA_DIR" \
  --top-n 3 \
  --max-hold-days 18 \
  --lookback-days 28 \
  --min-mom-lookback-pct 3.0 \
  --pullback-min-pct -12.0 \
  --pullback-max-pct -1.75 \
  --regime-min-breadth-sma-pct 60 \
  --regime-min-breadth-mom-pct 55 \
  --regime-min-avg-mom-pct 2.0 \
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
  --universe-top-k 10 \
  --universe-score-lookback-days 80 \
  --position-weight-mode score_inv_vol \
  --cluster-groups "$CLUSTER_GROUPS" \
  --max-per-cluster 1 \
  --forbid-pairs "$FORBID_PAIRS" \
  --stop-atr-mult 1.7 \
  --target-atr-mult 4.0 \
  --intramonth-portfolio-stop-pct 0.04 \
  --tag "$TAG"

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
EQ_LATEST_REFRESH_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
EQ_V35_ACTIVE_TICKERS=$ACTIVE_TICKERS
EOF

echo "latest_run_dir=$LATEST_RUN_DIR"
echo "latest_picks_csv=$LATEST_PICKS_CSV"
echo "latest_summary_csv=$LATEST_SUMMARY_CSV"
