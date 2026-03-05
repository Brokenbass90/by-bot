#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

python3 scripts/tax_monthly_report.py \
  --db "${TAX_DB_PATH:-trades.db}" \
  --csv "${TAX_FALLBACK_CSV:-}" \
  --tax-rate-pct "${TAX_RATE_PCT:-0}" \
  --from-month "${TAX_FROM_MONTH:-}" \
  --out-csv "${TAX_OUT_CSV:-docs/tax_monthly_latest.csv}" \
  --out-txt "${TAX_OUT_TXT:-docs/tax_monthly_latest.txt}"
