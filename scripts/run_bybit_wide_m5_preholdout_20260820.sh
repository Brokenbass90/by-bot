#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

OUT_ROOT="research_lab/data/bybit_wide137_m5_preholdout_20240301_20250930"
mkdir -p "$OUT_ROOT" logs

completed=0
failed=0
while IFS= read -r npz; do
  symbol="$(basename "$npz" .npz)"
  out_dir="$OUT_ROOT/$symbol"
  if [[ -s "$out_dir/$symbol.json" && -s "$out_dir/status.json" ]]; then
    echo "skip_complete=$symbol"
    completed=$((completed + 1))
    continue
  fi
  if .venv/bin/python scripts/materialize_bybit_5m_preholdout.py \
      --allow-public-network \
      --symbol "$symbol" \
      --start 2024-03-01 \
      --end-exclusive 2025-10-01 \
      --out-dir "$out_dir" \
      --min-free-gb 50; then
    completed=$((completed + 1))
  else
    echo "symbol_failed=$symbol"
    failed=$((failed + 1))
  fi
done < <(find research_lab/data/h1 -maxdepth 1 -type f -name '*.npz' | LC_ALL=C sort)

echo "wide_m5_preholdout_finished=1 completed=$completed failed=$failed"
test "$failed" -eq 0
