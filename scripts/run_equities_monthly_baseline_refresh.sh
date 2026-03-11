#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

CORE_TICKERS="${EQ_BASELINE_CORE_TICKERS:-AMD,GOOGL,META,NVDA,TSLA}"
BENCH_TICKERS="${EQ_BASELINE_BENCH_TICKERS:-SPY,QQQ}"
ALL_FETCH_TICKERS="${EQ_BASELINE_FETCH_TICKERS:-AMD,GOOGL,META,NVDA,TSLA,SPY,QQQ}"
DATA_DIR="${EQ_BASELINE_DATA_DIR:-data_cache/equities_1h}"
EARNINGS_CSV="${EQ_BASELINE_EARNINGS_CSV:-data_cache/equities/earnings_dates.csv}"

FETCH_PERIOD="${EQ_YF_PERIOD:-730d}"
FETCH_INTERVAL="${EQ_YF_INTERVAL:-60m}"
EARNINGS_LIMIT="${EQ_EARNINGS_LIMIT:-24}"
TAG="${EQ_BASELINE_TAG:-growth5_softcorr_invvol_refresh}"
RUNTIME_DIR="${EQ_BASELINE_RUNTIME_DIR:-runtime/equities_monthly}"

echo "equities monthly baseline refresh start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "core_tickers=${CORE_TICKERS}"
echo "bench_tickers=${BENCH_TICKERS}"
echo "data_dir=${DATA_DIR}"
echo "earnings_csv=${EARNINGS_CSV}"
echo "runtime_dir=${RUNTIME_DIR}"

EQ_TICKERS="$ALL_FETCH_TICKERS" \
EQ_YF_PERIOD="$FETCH_PERIOD" \
EQ_YF_INTERVAL="$FETCH_INTERVAL" \
EQ_DATA_DIR="$DATA_DIR" \
bash scripts/run_equities_fetch_yf.sh

EQ_TICKERS="$CORE_TICKERS" \
EQ_EARNINGS_LIMIT="$EARNINGS_LIMIT" \
EQ_EARNINGS_OUT_CSV="$EARNINGS_CSV" \
bash scripts/run_equities_fetch_earnings_yf.sh

python3 scripts/equities_monthly_research_sim.py \
  --tickers "$CORE_TICKERS" \
  --data-dir "$DATA_DIR" \
  --top-n 2 \
  --max-hold-days 15 \
  --lookback-days 60 \
  --regime-min-breadth-sma-pct 55 \
  --regime-min-breadth-mom-pct 55 \
  --regime-min-avg-mom-pct 2 \
  --earnings-csv "$EARNINGS_CSV" \
  --earnings-blackout-days-before 5 \
  --earnings-blackout-days-after 2 \
  --benchmark-tickers "$BENCH_TICKERS" \
  --benchmark-data-dir "$DATA_DIR" \
  --corr-lookback-days 60 \
  --corr-penalty-mult 3.0 \
  --corr-penalty-threshold 0.55 \
  --position-weight-mode inv_vol \
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
EOF

echo "latest_run_dir=$LATEST_RUN_DIR"
echo "latest_picks_csv=$LATEST_PICKS_CSV"
echo "latest_summary_csv=$LATEST_SUMMARY_CSV"
