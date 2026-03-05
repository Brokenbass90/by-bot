#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

# 1) Build monthly tax table first (uses trades db / optional csv fallback).
TAX_DB_PATH="${TAX_DB_PATH:-trades.db}" \
TAX_FALLBACK_CSV="${TAX_FALLBACK_CSV:-}" \
TAX_RATE_PCT="${TAX_RATE_PCT:-0}" \
TAX_FROM_MONTH="${TAX_FROM_MONTH:-}" \
TAX_OUT_CSV="${TAX_OUT_CSV:-docs/tax_monthly_latest.csv}" \
TAX_OUT_TXT="${TAX_OUT_TXT:-docs/tax_monthly_latest.txt}" \
bash scripts/run_tax_monthly_report.sh

# 2) Build consolidated monthly operator snapshot.
python3 scripts/build_operator_monthly_report.py \
  --tax-csv "${TAX_OUT_CSV:-docs/tax_monthly_latest.csv}" \
  --forex-active "${FX_ACTIVE_TXT:-docs/forex_combo_active_latest.txt}" \
  --equities-active "${EQ_ACTIVE_TXT:-docs/equities_combo_active_latest.txt}" \
  --forex-data-status "${FX_DATA_STATUS_CSV:-docs/forex_data_status.csv}" \
  --equities-data-status "${EQ_DATA_STATUS_CSV:-docs/equities_data_status.csv}" \
  --out-txt "${OP_REPORT_TXT:-docs/operator_monthly_latest.txt}" \
  --out-json "${OP_REPORT_JSON:-docs/operator_monthly_latest.json}"
