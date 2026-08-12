#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

export M15_BUDGET_S="${M15_BUDGET_S:-21600}"
export M15_OUTDIR="${M15_OUTDIR:-research_lab/data/m15_exec_v3}"
export M15_STATUS_PATH="${M15_STATUS_PATH:-research_lab/data/m15_exec_v3/build_status.json}"

exec "$REPO_ROOT/.venv/bin/python" research_lab/build_m15_bundle.py . research_lab/allowlist_v3.json
