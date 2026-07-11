#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
SPEC="$ROOT/configs/preregistered/frequent_crypto_20260711.json"
STAMP="${FREQUENT_CRYPTO_STAMP:-$(date -u +%Y%m%d_%H%M%S)}"
OUT="$ROOT/reports/research/frequent_crypto_prereg_20260711/$STAMP"
SYMBOLS="BTCUSDT,ETHUSDT,ATOMUSDT,AVAXUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,BCHUSDT,XLMUSDT,1000PEPEUSDT,HYPEUSDT,TAOUSDT,ONDOUSDT"
END="2026-07-04"

readonly ENGINE_SHA256="b96f9d10196fa6a1ca7371682cd5d91865abf3e2292f473fed3874bc17d144ac"
readonly RUN_PORTFOLIO_SHA256="85842dfaee4a32c6e1c20172258d37114df9db43d38a217f974e86f35784313c"
readonly ARS1_SHA256="bb19b78cdfb0ca6404d33c2ecb48d9f870acd979ffc10cea7064fb24b5ffc567"
readonly ASB2_SHA256="bbf1d445015f59bba60bcaeea03facfd7f519f40e51d218c61f268bb2684a3aa"

verify_hash() {
  local path="$1"
  local expected="$2"
  local actual
  actual="$(shasum -a 256 "$path" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    echo "FROZEN_SOURCE_MISMATCH path=$path expected=$expected actual=$actual" >&2
    return 3
  fi
}

verify_frozen_sources() {
  verify_hash backtest/engine.py "$ENGINE_SHA256"
  verify_hash backtest/run_portfolio.py "$RUN_PORTFOLIO_SHA256"
  verify_hash strategies/alt_range_scalp_v1.py "$ARS1_SHA256"
  verify_hash strategies/alt_support_bounce_v2.py "$ASB2_SHA256"
}

mkdir -p "$OUT"
"$PY" -m json.tool "$SPEC" >/dev/null
verify_frozen_sources
cp "$SPEC" "$OUT/preregistration.json"

echo "frequent crypto prereg start=$(date -u +%FT%TZ) stamp=$STAMP" | tee "$OUT/runner.log"
echo "code_head=$(git rev-parse HEAD)" | tee -a "$OUT/runner.log"
shasum -a 256 \
  backtest/engine.py \
  backtest/run_portfolio.py \
  strategies/alt_range_scalp_v1.py \
  strategies/alt_support_bounce_v2.py \
  scripts/run_frequent_crypto_preregistered_20260711.sh \
  "$SPEC" \
  | tee "$OUT/code_sha256.txt"
echo "risk_zero=1 broker_calls=0 symbols=$SYMBOLS" | tee -a "$OUT/runner.log"

"$PY" scripts/preflight_cache_coverage.py \
  --asset-class crypto \
  --cache-dir data_cache \
  --symbols "$SYMBOLS" \
  --days 360 \
  --end "$END" \
  --interval-min 5 \
  --min-coverage 0.98 \
  --max-gap-bars 12 \
  --strict \
  --out "$OUT/data_preflight_360d.csv" \
  2>&1 | tee "$OUT/data_preflight_360d.log"

run_ars1() {
  local label="$1"
  local side="$2"
  local adx="$3"
  local days="$4"
  local fee="$5"
  local slip="$6"
  local allow_longs="0"
  local allow_shorts="0"
  verify_frozen_sources
  if [[ "$side" == "long" ]]; then
    allow_longs="1"
  elif [[ "$side" == "short" ]]; then
    allow_shorts="1"
  else
    echo "invalid ARS1 side: $side" >&2
    return 2
  fi

  local tag="fc_20260711_${label}_${STAMP}"
  echo "case_start=$(date -u +%FT%TZ) tag=$tag" | tee -a "$OUT/runner.log"
  env \
    BACKTEST_CACHE_ONLY=1 \
    ALLOCATOR_ENABLE=0 \
    REGIME_ROUTER_ENABLE=0 \
    ARS1_SYMBOL_ALLOWLIST="$SYMBOLS" \
    ARS1_ALLOW_LONGS="$allow_longs" \
    ARS1_ALLOW_SHORTS="$allow_shorts" \
    ARS1_BB_PERIOD=20 \
    ARS1_BB_STD=2.0 \
    ARS1_MIN_BAND_WIDTH_PCT=1.5 \
    ARS1_MAX_BAND_WIDTH_PCT=24.0 \
    ARS1_RSI_LONG_MAX=38 \
    ARS1_RSI_SHORT_MIN=55 \
    ARS1_SL_ATR_MULT=0.8 \
    ARS1_TP1_FRAC=0.55 \
    ARS1_COOLDOWN_BARS_5M=12 \
    ARS1_MIN_BODY_FRAC=0.0 \
    ARS1_MIN_VOL_MULT=1.1 \
    ARS1_ADX_PERIOD=14 \
    ARS1_MAX_ADX="$adx" \
    ARS1_MIN_RR=1.15 \
    ARS1_MIN_STOP_PCT=0.0015 \
    ARS1_MAX_STOP_PCT=0.06 \
    ARS1_TIME_STOP_BARS_5M=216 \
    ARS1_TRAIL_ATR_MULT=0.0 \
    "$PY" backtest/run_portfolio.py \
      --cache data_cache \
      --symbols "$SYMBOLS" \
      --strategies alt_range_scalp_v1 \
      --days "$days" \
      --end "$END" \
      --tag "$tag" \
      --starting_equity 100 \
      --risk_pct 0.005 \
      --leverage 1 \
      --max_positions 4 \
      --cap_notional 30 \
      --fee_bps "$fee" \
      --slippage_bps "$slip" \
      --entry-on-next-open \
      2>&1 | tee "$OUT/${label}.log"
  echo "case_done=$(date -u +%FT%TZ) tag=$tag" | tee -a "$OUT/runner.log"
}

run_asb2() {
  local label="$1"
  local allow_descending="$2"
  local days="$3"
  local fee="$4"
  local slip="$5"
  local tag="fc_20260711_${label}_${STAMP}"
  verify_frozen_sources

  echo "case_start=$(date -u +%FT%TZ) tag=$tag" | tee -a "$OUT/runner.log"
  env \
    BACKTEST_CACHE_ONLY=1 \
    ALLOCATOR_ENABLE=0 \
    REGIME_ROUTER_ENABLE=0 \
    ASB2_SYMBOL_ALLOWLIST="$SYMBOLS" \
    ASB2_SIGNAL_TF=60 \
    ASB2_LOOKBACK=120 \
    ASB2_PIVOT_LEFT=2 \
    ASB2_PIVOT_RIGHT=2 \
    ASB2_MIN_TOUCHES=3 \
    ASB2_LEVEL_TOL_ATR=0.45 \
    ASB2_MAX_ENTRY_DIST_ATR=0.60 \
    ASB2_MIN_LOWER_WICK_FRAC=0.20 \
    ASB2_VOL_MULT=1.20 \
    ASB2_REQUIRE_HVN=0 \
    ASB2_ALLOW_FLAT=1 \
    ASB2_ALLOW_ASCENDING=1 \
    ASB2_ALLOW_DESCENDING="$allow_descending" \
    ASB2_SL_ATR_MULT=0.60 \
    ASB2_TP1_RR=1.0 \
    ASB2_TP2_RR=2.0 \
    ASB2_DESCENDING_TP2_RR=1.2 \
    ASB2_TRAIL_ATR_MULT=1.0 \
    ASB2_TRAIL_ACTIVATE_RR=1.0 \
    ASB2_BE_TRIGGER_RR=1.0 \
    ASB2_BE_LOCK_RR=0.2 \
    "$PY" backtest/run_portfolio.py \
      --cache data_cache \
      --symbols "$SYMBOLS" \
      --strategies alt_support_bounce_v2 \
      --days "$days" \
      --end "$END" \
      --tag "$tag" \
      --starting_equity 100 \
      --risk_pct 0.005 \
      --leverage 1 \
      --max_positions 4 \
      --cap_notional 30 \
      --fee_bps "$fee" \
      --slippage_bps "$slip" \
      --entry-on-next-open \
      2>&1 | tee "$OUT/${label}.log"
  echo "case_done=$(date -u +%FT%TZ) tag=$tag" | tee -a "$OUT/runner.log"
}

# Candidate 1: ARS1 side split. Same-universe ADX-off controls are mandatory.
run_ars1 "ars1_long_control_adx0_360d_base" long 0 360 6 2
run_ars1 "ars1_long_control_adx0_360d_stress" long 0 360 10 5
run_ars1 "ars1_long_adx25_360d_base" long 25 360 6 2
run_ars1 "ars1_long_adx25_360d_stress" long 25 360 10 5
run_ars1 "ars1_long_adx25_90d_stress" long 25 90 10 5

run_ars1 "ars1_short_control_adx0_360d_base" short 0 360 6 2
run_ars1 "ars1_short_control_adx0_360d_stress" short 0 360 10 5
run_ars1 "ars1_short_adx25_360d_base" short 25 360 6 2
run_ars1 "ars1_short_adx25_360d_stress" short 25 360 10 5
run_ars1 "ars1_short_adx25_90d_stress" short 25 90 10 5

# Candidate 2: ASB2 long-only. Descending-enabled control isolates one change.
run_asb2 "asb2_control_descending_360d_base" 1 360 6 2
run_asb2 "asb2_control_descending_360d_stress" 1 360 10 5
run_asb2 "asb2_nodescending_360d_base" 0 360 6 2
run_asb2 "asb2_nodescending_360d_stress" 0 360 10 5
run_asb2 "asb2_nodescending_90d_stress" 0 90 10 5

echo "frequent crypto prereg complete=$(date -u +%FT%TZ) stamp=$STAMP" | tee -a "$OUT/runner.log"
touch "$OUT/COMPLETE"
