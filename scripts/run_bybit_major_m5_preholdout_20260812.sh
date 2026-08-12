#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

exec >> logs/bybit_major_m5_preholdout_20260812.log 2>&1

OUT_ROOT="research_lab/data/bybit_major8_m5_preholdout_20240301_20250930"
mkdir -p "$OUT_ROOT"

for symbol in BTCUSDT SOLUSDT LINKUSDT ADAUSDT DOTUSDT SUIUSDT AVAXUSDT; do
  out_dir="$OUT_ROOT/$symbol"
  if [[ -s "$out_dir/$symbol.json" && -s "$out_dir/status.json" ]]; then
    echo "skip_complete=$symbol"
    continue
  fi
  .venv/bin/python scripts/materialize_bybit_5m_preholdout.py \
    --allow-public-network \
    --symbol "$symbol" \
    --start 2024-03-01 \
    --end-exclusive 2025-10-01 \
    --out-dir "$out_dir" \
    --min-free-gb 50
done

echo "major_m5_preholdout_complete=1"
