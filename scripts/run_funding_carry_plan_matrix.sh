#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

LOCAL_ENV="${FUNDING_PLAN_LOCAL_ENV:-configs/funding_carry_local.env}"
if [[ -f "$LOCAL_ENV" ]]; then
  set -a
  source "$LOCAL_ENV"
  set +a
fi

OUT_DIR="${FUNDING_PLAN_OUT_DIR:-runtime/funding_carry}"
CAPITAL="${FUNDING_PLAN_CAPITAL_USD:-500}"
MAX_SYMBOLS="${FUNDING_PLAN_MAX_SYMBOLS:-4}"
BASE_CSV="${FUNDING_PER_SYMBOL_CSV:-}"

echo "funding carry plan matrix start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "out_dir=${OUT_DIR}"

python3 scripts/funding_carry_live_plan.py \
  --per-symbol-csv "$BASE_CSV" \
  --capital-usd "$CAPITAL" \
  --max-symbols "$MAX_SYMBOLS" \
  --min-hist-net-usd 0.0 \
  --min-events 120 \
  --positive-carry-only 1 \
  --allow-borrow-legs 0 \
  --min-receive-8h-pct 0.005 \
  --max-abs-basis-pct 0.75 \
  --min-turnover-usd 50000000 \
  --min-oi-usd 10000000 \
  --out-dir "$OUT_DIR"

python3 scripts/funding_carry_live_plan.py \
  --per-symbol-csv "$BASE_CSV" \
  --capital-usd "$CAPITAL" \
  --max-symbols "$MAX_SYMBOLS" \
  --min-hist-net-usd 0.0 \
  --min-events 120 \
  --positive-carry-only 1 \
  --allow-borrow-legs 0 \
  --min-receive-8h-pct 0.0 \
  --max-abs-basis-pct 1.25 \
  --min-turnover-usd 20000000 \
  --min-oi-usd 5000000 \
  --out-dir "$OUT_DIR"
