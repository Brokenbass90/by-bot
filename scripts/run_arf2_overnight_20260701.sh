#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

RUN_ID="${RUN_ID:-arf2_overnight_20260701}"
SYMBOLS="${SYMBOLS:-1000PEPEUSDT,ADAUSDT,ATOMUSDT,AVAXUSDT,BCHUSDT,BNBUSDT,DOGEUSDT,DOTUSDT,HYPEUSDT,LINKUSDT,LTCUSDT,ONDOUSDT,SOLUSDT,SUIUSDT,TAOUSDT,XLMUSDT,XRPUSDT}"
DAYS="${DAYS:-360}"
LOG_DIR="logs/manual_research"
OUT_ROOT="reports/research/${RUN_ID}"
mkdir -p "$LOG_DIR" "$OUT_ROOT"

echo "[$(date -u +%FT%TZ)] ARF2 overnight start"
echo "RUN_ID=$RUN_ID"
echo "SYMBOLS=$SYMBOLS"
echo "DAYS=$DAYS"

echo "[$(date -u +%FT%TZ)] step=diagnostic"
.venv/bin/python scripts/arf2_ab_diagnostic.py \
  --symbols "$SYMBOLS" \
  --days "$DAYS" \
  --outdir "$OUT_ROOT/diagnostic"

run_portfolio_variant() {
  local name="$1"
  shift
  echo "[$(date -u +%FT%TZ)] step=portfolio name=$name"
  env BACKTEST_CACHE_ONLY=1 "$@" .venv/bin/python backtest/run_portfolio.py \
    --symbols "$SYMBOLS" \
    --strategies alt_resistance_fade_v2 \
    --days "$DAYS" \
    --entry-on-next-open \
    --fee_bps 6 \
    --slippage_bps 2 \
    --starting_equity 100 \
    --risk_pct 0.01 \
    --cap_notional 30 \
    --max_positions 3 \
    --tag "${RUN_ID}_${name}"
}

run_portfolio_variant old
run_portfolio_variant unified ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20
run_portfolio_variant unified_minrange1 ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20 ARF2_MIN_RANGE_PCT=1.0
run_portfolio_variant unified_retest025 ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20 ARF2_USE_RETEST_QUALITY=1 ARF2_RETEST_MIN_QUALITY=0.25
run_portfolio_variant unified_retest035 ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20 ARF2_USE_RETEST_QUALITY=1 ARF2_RETEST_MIN_QUALITY=0.35
run_portfolio_variant unified_retest045 ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20 ARF2_USE_RETEST_QUALITY=1 ARF2_RETEST_MIN_QUALITY=0.45
run_portfolio_variant unified_level_v12 ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20 ARF2_USE_LEVEL_ENTRY=1 ARF2_LEVEL_ENTRY_MAX_CHASE_ATR=2.0 ARF2_LEVEL_ENTRY_VALIDITY_BARS=12
run_portfolio_variant unified_level_v24 ARF2_USE_UNIFIED_LEVELS=1 ARF2_MIN_LEVEL_SCORE=0.20 ARF2_USE_LEVEL_ENTRY=1 ARF2_LEVEL_ENTRY_MAX_CHASE_ATR=2.0 ARF2_LEVEL_ENTRY_VALIDITY_BARS=24

echo "[$(date -u +%FT%TZ)] step=collect_summaries"
.venv/bin/python - <<'PY'
import csv
from pathlib import Path

run_id = "arf2_overnight_20260701"
rows = []
for p in sorted(Path("backtest_runs").glob(f"portfolio_*_{run_id}_*/summary.csv")):
    with p.open() as f:
        r = next(csv.DictReader(f))
    r["run_dir"] = str(p.parent)
    rows.append(r)
out = Path("reports/research") / run_id / "portfolio_summaries.csv"
out.parent.mkdir(parents=True, exist_ok=True)
if rows:
    keys = list(rows[0].keys())
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
md = out.with_suffix(".md")
lines = ["# ARF2 overnight portfolio summaries", ""]
if not rows:
    lines.append("No summaries found.")
else:
    lines += [
        "| tag | trades | net_pnl | PF | WR | DD |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(rows, key=lambda x: float(x.get("net_pnl") or 0), reverse=True):
        lines.append(
            f"| {r.get('tag')} | {r.get('trades')} | {r.get('net_pnl')} | "
            f"{r.get('profit_factor')} | {r.get('winrate')} | {r.get('max_drawdown')} |"
        )
md.write_text("\n".join(lines) + "\n")
print(out)
print(md)
PY

echo "[$(date -u +%FT%TZ)] ARF2 overnight done"

