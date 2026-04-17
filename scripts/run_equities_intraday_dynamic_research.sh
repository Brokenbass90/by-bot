#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_ENV="${ALPACA_BASE_LOCAL_ENV:-$ROOT/configs/alpaca_paper_local.env}"
DYNAMIC_ENV="${ALPACA_INTRADAY_DYNAMIC_ENV:-$ROOT/configs/alpaca_intraday_dynamic_v1.env}"

if [[ -f "$BASE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BASE_ENV"
  set +a
fi

if [[ -f "$DYNAMIC_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$DYNAMIC_ENV"
  set +a
fi

source .venv/bin/activate

LOOKBACK_DAYS="${EQ_RECENT_DAYS:-90}"
TOP_N="${EQ_WF_TOP_N:-8}"
MIN_TRADES="${EQ_MIN_TRADES:-20}"
DATA_DIR="${EQ_DATA_DIR:-data_cache/equities_1h}"
RUN_SUFFIX="${EQ_RUN_SUFFIX:-intraday_${LOOKBACK_DAYS}d_$$}"

END_DATE="${EQ_END_DATE:-}"
if [[ -z "$END_DATE" ]]; then
  END_DATE="$(python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
from forex.data import load_m5_csv
root = Path("data_cache/equities_1h/SPY_M5.csv")
if not root.exists():
    raise SystemExit("missing SPY_M5.csv for end-date discovery")
bars = load_m5_csv(str(root))
if not bars:
    raise SystemExit("empty SPY_M5.csv for end-date discovery")
print(datetime.fromtimestamp(bars[-1].ts, tz=timezone.utc).strftime("%Y-%m-%d"))
PY
)"
fi

START_DATE="$(python3 - "$END_DATE" "$LOOKBACK_DAYS" <<'PY'
from datetime import datetime, timedelta
import sys
end = datetime.strptime(sys.argv[1], "%Y-%m-%d")
lookback = int(sys.argv[2])
start = end - timedelta(days=lookback - 1)
print(start.strftime("%Y-%m-%d"))
PY
)"

python3 scripts/build_equities_intraday_watchlist.py \
  --data-dir "${INTRADAY_DATA_DIR:-data_cache/equities_1h}" \
  --max-symbols "${INTRADAY_DYNAMIC_MAX_SYMBOLS:-10}" \
  --breakout-target "${INTRADAY_DYNAMIC_BREAKOUT_TARGET:-5}" \
  --reversion-target "${INTRADAY_DYNAMIC_REVERSION_TARGET:-5}" \
  --min-avg-dollar-vol "${INTRADAY_DYNAMIC_MIN_AVG_DOLLAR_VOL:-25000000}" \
  --breakout-class "${INTRADAY_DYNAMIC_BREAKOUT_CLASS:-breakout_continuation}" \
  --reversion-class "${INTRADAY_DYNAMIC_REVERSION_CLASS:-grid_reversion}" \
  --end-date "${END_DATE}" \
  ${INTRADAY_DYNAMIC_SYMBOL_POOL:+--symbols "${INTRADAY_DYNAMIC_SYMBOL_POOL}"} \
  --out-json "${INTRADAY_CONFIG_FILE:-configs/intraday_config.json}"

export CFG_PATH="${INTRADAY_CONFIG_FILE:-configs/intraday_config.json}"

EQ_TICKERS="$(python3 - <<'PY'
import json
import os
from pathlib import Path
p = Path(os.environ.get("CFG_PATH", "configs/intraday_config.json"))
cfg = json.loads(p.read_text())
print(",".join(cfg.get("symbols") or []))
PY
)"

echo "equities intraday dynamic research start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "tickers=${EQ_TICKERS}"
echo "data_dir=${DATA_DIR}"
echo "date_range=${START_DATE}..${END_DATE}"

EQ_TICKERS="${EQ_TICKERS}" \
EQ_DATA_DIR="${DATA_DIR}" \
EQ_START_DATE="${START_DATE}" \
EQ_END_DATE="${END_DATE}" \
EQ_MIN_TRADES="${MIN_TRADES}" \
EQ_RUN_SUFFIX="${RUN_SUFFIX}" \
bash scripts/run_equities_strategy_scan.sh

LATEST_SCAN_DIR="$(ls -1dt backtest_runs/equities_scan_*_"${RUN_SUFFIX}" 2>/dev/null | head -n 1)"
if [[ -z "${LATEST_SCAN_DIR}" ]]; then
  echo "No scan dir found for suffix ${RUN_SUFFIX}" >&2
  exit 1
fi
EQ_SCAN_SUMMARY="${LATEST_SCAN_DIR}/summary.csv" \
EQ_DATA_DIR="${DATA_DIR}" \
EQ_START_DATE="${START_DATE}" \
EQ_END_DATE="${END_DATE}" \
EQ_WF_TOP_N="${TOP_N}" \
EQ_RUN_SUFFIX="${RUN_SUFFIX}" \
bash scripts/run_equities_walkforward_gate.sh

echo "equities intraday dynamic research done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
