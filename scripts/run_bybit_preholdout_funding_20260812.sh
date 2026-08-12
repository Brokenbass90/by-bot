#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

OUT="research_lab/data/bybit_public_preholdout_2023_20250930"
.venv/bin/python scripts/materialize_bybit_research_archive.py \
  --allow-public-network \
  --start 2023-01-01 \
  --as-of-exclusive 2025-10-01 \
  --out-dir "$OUT" \
  --min-free-gb 50 \
  --sleep-seconds 0.15

.venv/bin/python scripts/validate_bybit_research_archive.py "$OUT" \
  --out reports/evidence/BYBIT_PREHOLDOUT_FUNDING_VALIDATION_20260812.json
