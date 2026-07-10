#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SIDE="${1:-}"
if [[ "$SIDE" != "long" && "$SIDE" != "short" ]]; then
  echo "usage: $0 long|short" >&2
  exit 2
fi

SYMBOLS="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT"

for ELDER_MODE in off permissive strict; do
  OUT="reports/research/lm_${SIDE}_${ELDER_MODE}_20260710"
  echo "[$(date -u +%FT%TZ)] start side=$SIDE elder=$ELDER_MODE out=$OUT"
  PYTHONPATH=. BACKTEST_CACHE_ONLY=1 .venv/bin/python3 \
    scripts/run_crypto_level_memory_sweep_reclaim_20260707.py \
    --cache-dir .cache/klines \
    --days 180 \
    --end 2026-04-30 \
    --symbols "$SYMBOLS" \
    --lookbacks 48 \
    --respect 0.65 \
    --rr 1.2 \
    --min-touches 3 \
    --side "$SIDE" \
    --memory-bars 960 \
    --elder-mode "$ELDER_MODE" \
    --max-wall-sec 2400 \
    --out "$OUT"
  echo "[$(date -u +%FT%TZ)] done side=$SIDE elder=$ELDER_MODE"
done
