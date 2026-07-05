#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p logs/ivb1_long_bull_preflight_20260705

echo "[ivb1-long-bull] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[ivb1-long-bull] spec=configs/autoresearch/ivb1_long_bull_current360_preflight_20260705.json"

BACKTEST_CACHE_ONLY=1 CACHE_ONLY=1 \
  .venv/bin/python scripts/run_strategy_autoresearch.py \
    --spec configs/autoresearch/ivb1_long_bull_current360_preflight_20260705.json \
    --jobs 2

echo "[ivb1-long-bull] done_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
