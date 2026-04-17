#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export ALPACA_INTRADAY_DYNAMIC_ENV="${ALPACA_INTRADAY_DYNAMIC_ENV:-$ROOT/configs/alpaca_intraday_dynamic_v2_broad.env}"
export EQ_ANNUAL_RUN_SUFFIX="${EQ_ANNUAL_RUN_SUFFIX:-alpaca_dyn_broad_annual}"
export EQ_SEGMENT_DAYS="${EQ_SEGMENT_DAYS:-90}"
export EQ_SEGMENT_STEP_DAYS="${EQ_SEGMENT_STEP_DAYS:-90}"
export EQ_SEGMENT_COUNT="${EQ_SEGMENT_COUNT:-4}"

bash scripts/run_equities_intraday_dynamic_annual_segments.sh
