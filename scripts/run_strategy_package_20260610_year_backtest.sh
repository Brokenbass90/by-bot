#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

STAMP="${STAMP:-$(date -u +%Y%m%d_%H%M%S)}"
END_DATE="${END_DATE:-2026-06-11}"
DAYS="${DAYS:-365}"
STARTING_EQUITY="${STARTING_EQUITY:-100}"
RISK_PCT="${RISK_PCT:-0.01}"
LEVERAGE="${LEVERAGE:-3}"
MAX_POSITIONS="${MAX_POSITIONS:-3}"
FEE_BPS="${FEE_BPS:-6}"
SLIPPAGE_BPS="${SLIPPAGE_BPS:-2}"
CACHE_DIR="${CACHE_DIR:-.cache/klines}"
OUT_ROOT="${OUT_ROOT:-backtest_runs/strategy_package_20260610_year_${STAMP}}"

DEFAULT_SYMBOLS="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT,BNBUSDT,ONDOUSDT,DOGEUSDT,XRPUSDT,AVAXUSDT,BCHUSDT,XLMUSDT"
SYMBOLS="${SYMBOLS:-$DEFAULT_SYMBOLS}"

mkdir -p "$OUT_ROOT"

load_env_if_exists() {
  local path="$1"
  if [[ -f "$path" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$path"
    set +a
  fi
}

load_env_if_exists "configs/approved_strategy_params.env"
load_env_if_exists "configs/dynamic_allowlist_latest.env"
load_env_if_exists "configs/elder_strict_majors_20260610.env"

# Package-level, explicit risk profile for honest combined tests.
export NO_ENTRY_HOURS_UTC=""
export ATT1_RISK_MULT="${ATT1_RISK_MULT:-0.70}"
export ATT2_USE_ATT1_ENV="${ATT2_USE_ATT1_ENV:-1}"
export ATT2_RISK_MULT="${ATT2_RISK_MULT:-0.70}"
export FLAT_RISK_MULT="${FLAT_RISK_MULT:-0.70}"
export BREAKDOWN_RISK_MULT="${BREAKDOWN_RISK_MULT:-0.50}"
export BOUNCE1_RISK_MULT="${BOUNCE1_RISK_MULT:-1.00}"
export MIDTERM_RISK_MULT="${MIDTERM_RISK_MULT:-0.50}"
export ELDER_RISK_MULT="${ELDER_RISK_MULT:-0.50}"
export ELDER_V2_RISK_MULT="${ELDER_V2_RISK_MULT:-$ELDER_RISK_MULT}"
export MSCALP_RISK_MULT="${MSCALP_RISK_MULT:-0.50}"
export GS1_RISK_MULT="${GS1_RISK_MULT:-0.30}"
export IVB1_RISK_MULT="${IVB1_RISK_MULT:-0.00}"
export HZBO1_RISK_MULT="${HZBO1_RISK_MULT:-0.00}"
export ASB1_RISK_MULT="${ASB1_RISK_MULT:-0.00}"
export PORTFOLIO_GLOBAL_SL_COOLDOWN_BARS="${PORTFOLIO_GLOBAL_SL_COOLDOWN_BARS:-48}"
export PORTFOLIO_GLOBAL_SL_STRATEGIES="${PORTFOLIO_GLOBAL_SL_STRATEGIES:-alt_inplay_breakdown_v1}"

run_case() {
  local name="$1"
  local strategies="$2"
  local max_pos="${3:-$MAX_POSITIONS}"
  local risk_pct="${4:-$RISK_PCT}"
  local tag="pkg20260610_${name}_${DAYS}d_${STAMP}"
  local log="$OUT_ROOT/${name}.log"
  echo "=== ${name} ===" | tee -a "$OUT_ROOT/run.log"
  echo "strategies=${strategies}" | tee -a "$OUT_ROOT/run.log"
  python3 backtest/run_portfolio.py \
    --symbols "$SYMBOLS" \
    --strategies "$strategies" \
    --days "$DAYS" \
    --end "$END_DATE" \
    --starting_equity "$STARTING_EQUITY" \
    --risk_pct "$risk_pct" \
    --leverage "$LEVERAGE" \
    --max_positions "$max_pos" \
    --fee_bps "$FEE_BPS" \
    --slippage_bps "$SLIPPAGE_BPS" \
    --cache "$CACHE_DIR" \
    --tag "$tag" 2>&1 | tee "$log"
  local run_dir
  run_dir="$(grep -E '^  out:' "$log" | tail -1 | awk '{print $2}')"
  if [[ -n "${run_dir:-}" && -d "$run_dir" ]]; then
    echo "${name},${run_dir}" >> "$OUT_ROOT/run_dirs.csv"
  fi
}

echo "name,run_dir" > "$OUT_ROOT/run_dirs.csv"
{
  echo "stamp=$STAMP"
  echo "end=$END_DATE days=$DAYS symbols=$SYMBOLS"
  echo "risk=$RISK_PCT lev=$LEVERAGE max_positions=$MAX_POSITIONS fee_bps=$FEE_BPS slippage_bps=$SLIPPAGE_BPS"
} > "$OUT_ROOT/manifest.txt"

run_case "core_live_v1" \
  "alt_support_bounce_v1,alt_resistance_fade_v1,alt_trendline_touch_v1,alt_inplay_breakdown_v1,btc_eth_midterm_pullback,elder_triple_screen_v2"

run_case "core_att2_challenger" \
  "alt_support_bounce_v1,alt_resistance_fade_v1,alt_trendline_touch_v2,alt_inplay_breakdown_v1,btc_eth_midterm_pullback,elder_triple_screen_v2"

run_case "full_candidates_att2" \
  "alt_support_bounce_v1,alt_resistance_fade_v1,alt_trendline_touch_v2,alt_inplay_breakdown_v1,btc_eth_midterm_pullback,elder_triple_screen_v2,micro_scalper_v1,grid_smart_v1"

run_case "micro_scalper_only" \
  "micro_scalper_v1" \
  1 \
  "$RISK_PCT"

run_case "grid_smart_only" \
  "grid_smart_v1"

python3 - "$OUT_ROOT/run_dirs.csv" "$OUT_ROOT/summary.csv" <<'PY'
import csv, json, pathlib, sys

run_dirs_path = pathlib.Path(sys.argv[1])
out_path = pathlib.Path(sys.argv[2])
rows = []
with run_dirs_path.open(newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        name = row["name"]
        run_dir = pathlib.Path(row["run_dir"])
        summary = run_dir / "summary.csv"
        if not summary.exists():
            continue
        with summary.open(newline="", encoding="utf-8") as sf:
            data = next(csv.DictReader(sf))
        data = {"case": name, "run_dir": str(run_dir), **data}
        rows.append(data)

if rows:
    keys = [
        "case", "strategies", "symbols", "days", "trades", "net_pnl",
        "return_pct", "profit_factor", "winrate", "max_drawdown", "run_dir",
    ]
    extra = [k for k in rows[0].keys() if k not in keys]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in keys if k in rows[0]] + extra)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"summary={out_path}")
    for row in rows:
        print(
            f"{row.get('case')}: trades={row.get('trades')} "
            f"return={row.get('return_pct')} pf={row.get('profit_factor')} "
            f"dd={row.get('max_drawdown')}"
        )
else:
    print("summary=no_rows")
PY

echo "saved=$OUT_ROOT"
