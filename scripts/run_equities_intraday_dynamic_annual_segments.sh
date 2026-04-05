#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

SEGMENT_DAYS="${EQ_SEGMENT_DAYS:-90}"
SEGMENT_STEP_DAYS="${EQ_SEGMENT_STEP_DAYS:-90}"
SEGMENT_COUNT="${EQ_SEGMENT_COUNT:-4}"
RUN_SUFFIX_BASE="${EQ_ANNUAL_RUN_SUFFIX:-alpaca_dyn_annual}"

ANCHOR_END_DATE="${EQ_END_DATE:-}"
if [[ -z "$ANCHOR_END_DATE" ]]; then
  ANCHOR_END_DATE="$(python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
from forex.data import load_m5_csv
p = Path("data_cache/equities_1h/SPY_M5.csv")
if not p.exists():
    raise SystemExit("missing SPY_M5.csv for anchor end date discovery")
bars = load_m5_csv(str(p))
if not bars:
    raise SystemExit("empty SPY_M5.csv for anchor end date discovery")
print(datetime.fromtimestamp(bars[-1].ts, tz=timezone.utc).strftime("%Y-%m-%d"))
PY
)"
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT_DIR="backtest_runs/equities_intraday_dynamic_annual_${STAMP}_${RUN_SUFFIX_BASE}"
mkdir -p "$OUT_DIR"
MANIFEST="${OUT_DIR}/segments.csv"
echo "segment_idx,segment_end,segment_days,run_suffix,scan_dir,wf_dir" > "$MANIFEST"

echo "equities intraday dynamic annual segmented research start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "anchor_end_date=${ANCHOR_END_DATE}"
echo "segment_days=${SEGMENT_DAYS} step_days=${SEGMENT_STEP_DAYS} count=${SEGMENT_COUNT}"
echo "out_dir=${OUT_DIR}"

for ((i=0; i<SEGMENT_COUNT; i++)); do
  SEG_END="$(python3 - "$ANCHOR_END_DATE" "$SEGMENT_STEP_DAYS" "$i" <<'PY'
from datetime import datetime, timedelta
import sys
anchor = datetime.strptime(sys.argv[1], "%Y-%m-%d")
step = int(sys.argv[2])
idx = int(sys.argv[3])
seg_end = anchor - timedelta(days=step * idx)
print(seg_end.strftime("%Y-%m-%d"))
PY
)"
  RUN_SUFFIX="${RUN_SUFFIX_BASE}_s$(printf '%02d' $((i+1)))_${SEG_END//-/}"
  echo ""
  echo "=== segment $((i+1)) / ${SEGMENT_COUNT} | end=${SEG_END} | suffix=${RUN_SUFFIX} ==="

  EQ_RECENT_DAYS="${SEGMENT_DAYS}" \
  EQ_END_DATE="${SEG_END}" \
  EQ_RUN_SUFFIX="${RUN_SUFFIX}" \
  bash scripts/run_equities_intraday_dynamic_research.sh

  SCAN_DIR="$(ls -1dt backtest_runs/equities_scan_*_"${RUN_SUFFIX}" 2>/dev/null | head -n 1)"
  WF_DIR="$(ls -1dt backtest_runs/equities_wf_gate_*_"${RUN_SUFFIX}" 2>/dev/null | head -n 1)"
  echo "$((i+1)),${SEG_END},${SEGMENT_DAYS},${RUN_SUFFIX},${SCAN_DIR},${WF_DIR}" >> "$MANIFEST"
done

echo ""
echo "equities intraday dynamic annual segmented research done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "manifest=${MANIFEST}"
