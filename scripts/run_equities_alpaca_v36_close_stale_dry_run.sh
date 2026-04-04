#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export ALPACA_CANDIDATE_ENV="${ALPACA_CANDIDATE_ENV:-$ROOT/configs/alpaca_paper_v36_close_stale_dry_run.env}"

bash scripts/run_equities_alpaca_v36_candidate.sh "$@"
