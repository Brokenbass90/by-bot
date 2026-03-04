#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY}"
DATA_DIR="${FX_DATA_DIR:-data_cache/forex}"
YF_PERIOD="${FX_YF_PERIOD:-60d}"
YF_INTERVAL="${FX_YF_INTERVAL:-5m}"
TAG="${FX_OVERNIGHT_TAG:-fx_overnight}"
MAX_ACTIVE="${FX_MAX_ACTIVE_COMBOS:-4}"

echo "forex overnight research start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS}"
echo "data_dir=${DATA_DIR}"
echo "yf period=${YF_PERIOD} interval=${YF_INTERVAL}"

echo ""
echo ">>> STEP 1: FETCH (yfinance)"
FX_PAIRS="${PAIRS}" \
FX_DATA_DIR="${DATA_DIR}" \
FX_YF_PERIOD="${YF_PERIOD}" \
FX_YF_INTERVAL="${YF_INTERVAL}" \
bash scripts/run_forex_fetch_yf.sh || true

echo ""
echo ">>> STEP 2: DATA CHECK"
FX_PAIRS="${PAIRS}" FX_DATA_DIR="${DATA_DIR}" bash scripts/run_forex_data_check.sh

echo ""
echo ">>> STEP 3: TWO-STAGE GATE + STATE UPDATE"
FX_PAIRS="${PAIRS}" \
FX_FAST_TAG="${TAG}_fast" \
FX_FULL_TAG="${TAG}_full" \
FX_MAX_ACTIVE_COMBOS="${MAX_ACTIVE}" \
FX_INCLUDE_ACTIVE_IN_FULL="${FX_INCLUDE_ACTIVE_IN_FULL:-1}" \
bash scripts/run_forex_two_stage_gate.sh

echo ""
echo ">>> STEP 4: ACTIVE HEALTH"
python3 scripts/run_forex_active_health_check.py

echo ""
echo ">>> STEP 5: SNAPSHOT"
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path

root = Path(".")
out = root / "docs" / "forex_overnight_latest.txt"
active = (root / "docs" / "forex_combo_active_latest.txt").read_text(encoding="utf-8", errors="ignore").strip()
canary = (root / "docs" / "forex_live_canary_combos_latest.txt").read_text(encoding="utf-8", errors="ignore").strip()
health = (root / "docs" / "forex_active_health_latest.txt").read_text(encoding="utf-8", errors="ignore").strip()

lines = [
    f"generated_utc={datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    f"active={active or '-'}",
    f"canary={canary or '-'}",
    "",
    "health:",
    health or "-",
]
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"saved={out.resolve()}")
PY

echo ""
echo "forex overnight research done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
