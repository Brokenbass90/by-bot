#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

# ── Universe (v37: expanded from 44 → 57 tickers) ─────────────────────────────
# Added: TSM QCOM TXN (semis breadth), NOW INTU ADSK (enterprise SaaS),
#        WFC SCHW (finance breadth), REGN ISRG (healthcare quality),
#        PG KO (defensive consumer staples for bear-regime diversification)
# Block Inc changed its public ticker from SQ to XYZ; use XYZ for live order safety.
TICKERS="${EQ_V36_TICKERS:-AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM,CRM,COIN,SHOP,XYZ,SNOW,NET,DDOG,MDB,ABNB,GS,V,MA,BAC,CVX,CAT,GE,LMT,UNH,LLY,ABBV,JNJ,MRK,COST,WMT,HD,NKE,SBUX,TSM,QCOM,TXN,NOW,INTU,ADSK,WFC,SCHW,REGN,ISRG,PG,KO}"
BENCH_TICKERS="${EQ_V36_BENCH_TICKERS:-SPY,QQQ}"
ALL_FETCH_TICKERS="${EQ_V36_FETCH_TICKERS:-${TICKERS},${BENCH_TICKERS}}"
DATA_DIR="${EQ_V36_DATA_DIR:-data_cache/equities_1h}"
EARNINGS_CSV="${EQ_V36_EARNINGS_CSV:-data_cache/equities/earnings_dates.csv}"
# Sector map for sector-cap enforcement (max 1 pick from same sector by default)
SECTOR_MAP="${EQ_V36_SECTOR_MAP:-AAPL:Tech,MSFT:Tech,GOOGL:Tech,AMZN:Tech,META:Tech,NVDA:Semis,AMD:Semis,AVGO:Semis,TSM:Semis,QCOM:Semis,TXN:Semis,ADBE:SaaS,CRM:SaaS,ORCL:SaaS,NOW:SaaS,INTU:SaaS,ADSK:SaaS,CRWD:Cyber,PANW:Cyber,NET:Cyber,DDOG:Cyber,SNOW:Cyber,MDB:Cyber,PLTR:GrowthTech,UBER:GrowthTech,SHOP:GrowthTech,COIN:GrowthTech,XYZ:GrowthTech,NFLX:Media,ABNB:Media,JPM:Finance,GS:Finance,BAC:Finance,V:Finance,MA:Finance,WFC:Finance,SCHW:Finance,XOM:Energy,CVX:Energy,CAT:Industrial,GE:Industrial,LMT:Industrial,UNH:Health,LLY:Health,ABBV:Health,JNJ:Health,MRK:Health,REGN:Health,ISRG:Health,COST:Consumer,WMT:Consumer,HD:Consumer,NKE:Consumer,SBUX:Consumer,PG:Staples,KO:Staples,TSLA:Auto}"
MAX_PER_SECTOR="${EQ_V36_MAX_PER_SECTOR:-2}"
CLUSTER_GROUPS="${EQ_V36_CLUSTER_GROUPS:-AAPL,MSFT,GOOGL,AMZN,META;NVDA,AMD,AVGO,TSM,QCOM,TXN;ADBE,CRM,ORCL,NOW,INTU,ADSK;META,NFLX,ABNB;CRWD,PANW,NET,DDOG,SNOW,MDB;PLTR,UBER,SHOP,COIN,XYZ;JPM,GS,BAC,V,MA,WFC,SCHW;XOM,CVX;CAT,GE,LMT;UNH,LLY,ABBV,JNJ,MRK,REGN,ISRG;COST,WMT,HD,NKE,SBUX,PG,KO;TSLA}"
FORBID_PAIRS="${EQ_V36_FORBID_PAIRS:-NVDA:AMD;NVDA:TSM;CRWD:PANW;META:NFLX;V:MA;WFC:BAC;LLY:ABBV}"
# Earnings blackout: skip picks 3 days before / 1 day after earnings report
EARNINGS_BLACKOUT_DAYS_BEFORE="${EQ_V36_EARNINGS_BLACKOUT_DAYS_BEFORE:-3}"
EARNINGS_BLACKOUT_DAYS_AFTER="${EQ_V36_EARNINGS_BLACKOUT_DAYS_AFTER:-1}"

FETCH_PERIOD="${EQ_V36_YF_PERIOD:-730d}"
FETCH_INTERVAL="${EQ_V36_YF_INTERVAL:-60m}"
EARNINGS_LIMIT="${EQ_V36_EARNINGS_LIMIT:-24}"
TAG="${EQ_V36_TAG:-equities_monthly_v38_candidate_refresh}"
RUNTIME_DIR="${EQ_V36_RUNTIME_DIR:-runtime/equities_monthly_v36}"

SIM_START_MONTH="${EQ_V36_SIM_START_MONTH:-2024-05}"
SIM_END_MONTH="${EQ_V36_SIM_END_MONTH:-2026-04}"
SIM_TOP_N="${EQ_V36_SIM_TOP_N:-3}"
SIM_MAX_HOLD_DAYS="${EQ_V36_SIM_MAX_HOLD_DAYS:-20}"
SIM_MIN_MOM_LOOKBACK_PCT="${EQ_V36_SIM_MIN_MOM_LOOKBACK_PCT:-5.0}"
SIM_STOP_ATR_MULT="${EQ_V36_SIM_STOP_ATR_MULT:-2.0}"
SIM_TARGET_ATR_MULT="${EQ_V36_SIM_TARGET_ATR_MULT:-2.8}"
SIM_INTRAMONTH_PORTFOLIO_STOP_PCT="${EQ_V36_SIM_INTRAMONTH_PORTFOLIO_STOP_PCT:-0.08}"
SIM_BE_TRIGGER_R="${EQ_V36_SIM_BE_TRIGGER_R:-0.8}"
SIM_TRAIL_ATR_MULT="${EQ_V36_SIM_TRAIL_ATR_MULT:-1.5}"
SIM_REGIME_MIN_BREADTH_SMA_PCT="${EQ_V36_SIM_REGIME_MIN_BREADTH_SMA_PCT:-60}"
SIM_REGIME_MIN_BREADTH_MOM_PCT="${EQ_V36_SIM_REGIME_MIN_BREADTH_MOM_PCT:-45}"
SIM_REGIME_MIN_AVG_MOM_PCT="${EQ_V36_SIM_REGIME_MIN_AVG_MOM_PCT:-1.5}"

CURRENT_TOP_N="${EQ_V36_CURRENT_TOP_N:-3}"
# Candidate pool can be wider than the bridge max position count. The paper
# bridge still buys only ALPACA_MAX_POSITIONS, but a wider pool prevents
# selected=[] when top names are temporarily blocked by re-entry protection.
CURRENT_CANDIDATE_POOL_N="${EQ_V36_CURRENT_CANDIDATE_POOL_N:-$CURRENT_TOP_N}"
CURRENT_LOOKBACK_DAYS="${EQ_V36_CURRENT_LOOKBACK_DAYS:-28}"
CURRENT_MIN_MOM_LOOKBACK_PCT="${EQ_V36_CURRENT_MIN_MOM_LOOKBACK_PCT:-5.0}"
CURRENT_PULLBACK_MIN_PCT="${EQ_V36_CURRENT_PULLBACK_MIN_PCT:-12.0}"
CURRENT_PULLBACK_MAX_PCT="${EQ_V36_CURRENT_PULLBACK_MAX_PCT:-1.5}"
CURRENT_BENCHMARK_MIN_ABOVE_SMA_COUNT="${EQ_V36_CURRENT_BENCHMARK_MIN_ABOVE_SMA_COUNT:-1}"
CURRENT_CORR_LOOKBACK_DAYS="${EQ_V36_CURRENT_CORR_LOOKBACK_DAYS:-60}"
CURRENT_MAX_PAIR_CORR="${EQ_V36_CURRENT_MAX_PAIR_CORR:-0.75}"
CURRENT_CORR_PENALTY_MULT="${EQ_V36_CURRENT_CORR_PENALTY_MULT:-2.5}"
CURRENT_CORR_PENALTY_THRESHOLD="${EQ_V36_CURRENT_CORR_PENALTY_THRESHOLD:-0.5}"
CURRENT_UNIVERSE_TOP_K="${EQ_V36_CURRENT_UNIVERSE_TOP_K:-14}"
CURRENT_UNIVERSE_SCORE_LOOKBACK_DAYS="${EQ_V36_CURRENT_UNIVERSE_SCORE_LOOKBACK_DAYS:-80}"
CURRENT_POSITION_WEIGHT_MODE="${EQ_V36_CURRENT_POSITION_WEIGHT_MODE:-score_inv_vol}"
CURRENT_MAX_PER_CLUSTER="${EQ_V36_CURRENT_MAX_PER_CLUSTER:-1}"
CURRENT_STOP_ATR_MULT="${EQ_V36_CURRENT_STOP_ATR_MULT:-2.0}"
CURRENT_TARGET_ATR_MULT="${EQ_V36_CURRENT_TARGET_ATR_MULT:-2.8}"

CURRENT_RELAXED_MIN_MOM_LOOKBACK_PCT="${EQ_V36_CURRENT_RELAXED_MIN_MOM_LOOKBACK_PCT:-0.0}"
CURRENT_RELAXED_PULLBACK_MIN_PCT="${EQ_V36_CURRENT_RELAXED_PULLBACK_MIN_PCT:--20.0}"
CURRENT_RELAXED_PULLBACK_MAX_PCT="${EQ_V36_CURRENT_RELAXED_PULLBACK_MAX_PCT:-1.0}"
CURRENT_RELAXED_MAX_PAIR_CORR="${EQ_V36_CURRENT_RELAXED_MAX_PAIR_CORR:-0.90}"
CURRENT_RELAXED_UNIVERSE_TOP_K="${EQ_V36_CURRENT_RELAXED_UNIVERSE_TOP_K:-30}"

run_current_cycle_builder() {
  python3 scripts/build_equities_monthly_live_cycle.py \
    --tickers "$TICKERS" \
    --data-dir "$DATA_DIR" \
    --top-n "$1" \
    --lookback-days "$2" \
    --min-mom-lookback-pct "$3" \
    --pullback-min-pct "$4" \
    --pullback-max-pct "$5" \
    --benchmark-tickers "$BENCH_TICKERS" \
    --benchmark-data-dir "$DATA_DIR" \
    --benchmark-lookback-days 60 \
    --benchmark-min-above-sma-count "$6" \
    --corr-lookback-days "$7" \
    --max-pair-corr "$8" \
    --corr-penalty-mult "$9" \
    --corr-penalty-threshold "${10}" \
    --universe-top-k "${11}" \
    --universe-score-lookback-days "${12}" \
    --position-weight-mode "${13}" \
    --cluster-groups "$CLUSTER_GROUPS" \
    --max-per-cluster "${14}" \
    --stop-atr-mult "${15}" \
    --target-atr-mult "${16}" \
    --earnings-csv "$EARNINGS_CSV" \
    --earnings-blackout-days-before "$EARNINGS_BLACKOUT_DAYS_BEFORE" \
    --earnings-blackout-days-after "$EARNINGS_BLACKOUT_DAYS_AFTER" \
    --sector-map "$SECTOR_MAP" \
    --max-per-sector "$MAX_PER_SECTOR" \
    --out-picks-csv "$RUNTIME_DIR/current_cycle_picks.csv" \
    --out-summary-csv "$RUNTIME_DIR/current_cycle_summary.csv"
}

echo "equities monthly v36 refresh start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "tickers=${TICKERS}"
echo "bench_tickers=${BENCH_TICKERS}"
echo "data_dir=${DATA_DIR}"
echo "earnings_csv=${EARNINGS_CSV}"
echo "runtime_dir=${RUNTIME_DIR}"
echo "sim_months=${SIM_START_MONTH}..${SIM_END_MONTH}"
echo "sim_top_n=${SIM_TOP_N}"
echo "current_candidate_pool_n=${CURRENT_CANDIDATE_POOL_N} max_live_positions_hint=${ALPACA_MAX_POSITIONS:-unset}"

if [[ "${EQ_V36_RESEARCH_ONLY:-0}" == "1" ]]; then
  echo "research_only=1; using existing cache and leaving current-cycle runtime untouched"
else
  EQ_TICKERS="$ALL_FETCH_TICKERS" \
  EQ_YF_PERIOD="$FETCH_PERIOD" \
  EQ_YF_INTERVAL="$FETCH_INTERVAL" \
  EQ_DATA_DIR="$DATA_DIR" \
  bash scripts/run_equities_fetch_yf.sh

  EQ_TICKERS="$TICKERS" \
  EQ_EARNINGS_LIMIT="$EARNINGS_LIMIT" \
  EQ_EARNINGS_OUT_CSV="$EARNINGS_CSV" \
  bash scripts/run_equities_fetch_earnings_yf.sh
fi

python3 scripts/equities_monthly_research_sim.py \
  --tickers "$TICKERS" \
  --data-dir "$DATA_DIR" \
  --top-n "$SIM_TOP_N" \
  --max-hold-days "$SIM_MAX_HOLD_DAYS" \
  --lookback-days 28 \
  --min-mom-lookback-pct "$SIM_MIN_MOM_LOOKBACK_PCT" \
  --pullback-min-pct -12.0 \
  --pullback-max-pct -1.5 \
  --regime-min-breadth-sma-pct "$SIM_REGIME_MIN_BREADTH_SMA_PCT" \
  --regime-min-breadth-mom-pct "$SIM_REGIME_MIN_BREADTH_MOM_PCT" \
  --regime-min-avg-mom-pct "$SIM_REGIME_MIN_AVG_MOM_PCT" \
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
  --stop-atr-mult "$SIM_STOP_ATR_MULT" \
  --target-atr-mult "$SIM_TARGET_ATR_MULT" \
  --intramonth-portfolio-stop-pct "$SIM_INTRAMONTH_PORTFOLIO_STOP_PCT" \
  --be-trigger-r "$SIM_BE_TRIGGER_R" \
  --trail-atr-mult "$SIM_TRAIL_ATR_MULT" \
  --start-month "$SIM_START_MONTH" \
  --end-month "$SIM_END_MONTH" \
  --tag "$TAG"

if [[ "${EQ_V36_RESEARCH_ONLY:-0}" == "1" ]]; then
  echo "research_only=1 complete; skipped current-cycle builder and runtime publish"
  exit 0
fi

if ! run_current_cycle_builder \
  "$CURRENT_CANDIDATE_POOL_N" \
  "$CURRENT_LOOKBACK_DAYS" \
  "$CURRENT_MIN_MOM_LOOKBACK_PCT" \
  "$CURRENT_PULLBACK_MIN_PCT" \
  "$CURRENT_PULLBACK_MAX_PCT" \
  "$CURRENT_BENCHMARK_MIN_ABOVE_SMA_COUNT" \
  "$CURRENT_CORR_LOOKBACK_DAYS" \
  "$CURRENT_MAX_PAIR_CORR" \
  "$CURRENT_CORR_PENALTY_MULT" \
  "$CURRENT_CORR_PENALTY_THRESHOLD" \
  "$CURRENT_UNIVERSE_TOP_K" \
  "$CURRENT_UNIVERSE_SCORE_LOOKBACK_DAYS" \
  "$CURRENT_POSITION_WEIGHT_MODE" \
  "$CURRENT_MAX_PER_CLUSTER" \
  "$CURRENT_STOP_ATR_MULT" \
  "$CURRENT_TARGET_ATR_MULT"; then
  echo "warn: strict current-cycle builder produced no fresh picks"
  echo "info: retrying current-cycle builder with relaxed profile"
  if ! run_current_cycle_builder \
    "$CURRENT_CANDIDATE_POOL_N" \
    "$CURRENT_LOOKBACK_DAYS" \
    "$CURRENT_RELAXED_MIN_MOM_LOOKBACK_PCT" \
    "$CURRENT_RELAXED_PULLBACK_MIN_PCT" \
    "$CURRENT_RELAXED_PULLBACK_MAX_PCT" \
    "$CURRENT_BENCHMARK_MIN_ABOVE_SMA_COUNT" \
    "$CURRENT_CORR_LOOKBACK_DAYS" \
    "$CURRENT_RELAXED_MAX_PAIR_CORR" \
    "$CURRENT_CORR_PENALTY_MULT" \
    "$CURRENT_CORR_PENALTY_THRESHOLD" \
    "$CURRENT_RELAXED_UNIVERSE_TOP_K" \
    "$CURRENT_UNIVERSE_SCORE_LOOKBACK_DAYS" \
    "$CURRENT_POSITION_WEIGHT_MODE" \
    "$CURRENT_MAX_PER_CLUSTER" \
    "$CURRENT_STOP_ATR_MULT" \
    "$CURRENT_TARGET_ATR_MULT"; then
    echo "warn: current-cycle builder produced no fresh picks even after relaxed retry"
    rm -f "$RUNTIME_DIR/current_cycle_picks.csv" "$RUNTIME_DIR/current_cycle_summary.csv"
  fi
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
ALPACA_CURRENT_CYCLE_PICKS_CSV=$RUNTIME_DIR/current_cycle_picks.csv
ALPACA_CURRENT_CYCLE_SUMMARY_CSV=$RUNTIME_DIR/current_cycle_summary.csv
ALPACA_REFRESH_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
EQ_V36_ACTIVE_TICKERS=$TICKERS
EOF

echo "latest_run_dir=$LATEST_RUN_DIR"
echo "latest_picks_csv=$LATEST_PICKS_CSV"
echo "latest_summary_csv=$LATEST_SUMMARY_CSV"
