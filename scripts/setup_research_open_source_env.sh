#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${RESEARCH_PYTHON_BIN:-python3.12}"
VENV="${ROOT}/.venv-research"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Missing ${PYTHON_BIN}; install Python 3.12 for the isolated research runtime." >&2
  exit 2
fi

if [[ ! -x "${VENV}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install \
  --requirement "${ROOT}/requirements-research-open-source.txt"
"${VENV}/bin/python" "${ROOT}/scripts/smoke_research_open_source_stack.py"
