#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${1:-$ROOT/runtime/research/event_universe_v2r2_20260721_public1}"
OUTPUT_DIR="$ROOT/reports/research/event_universe_v1_labels"
COLLECTOR_SCREEN="${2:-event_universe_v2r2_20260721}"

case "$COLLECTOR_SCREEN" in
  *[!A-Za-z0-9_.-]*)
    echo "invalid collector screen name" >&2
    exit 2
    ;;
esac

echo "postrun label gate waiting for collector: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
while screen -ls 2>/dev/null | grep -Fq ".${COLLECTOR_SCREEN}"; do
  sleep 60
done

echo "collector stopped; running frozen local label scorer: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$ROOT/.venv/bin/python" "$ROOT/scripts/score_event_universe_v1.py" \
  --run-root "$RUN_ROOT" \
  --output-dir "$OUTPUT_DIR"

"$ROOT/.venv/bin/python" "$ROOT/scripts/build_crypto_event_rehab_status.py"
echo "postrun label gate complete: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
