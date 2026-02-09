#!/usr/bin/env bash
set -euo pipefail

# Bootstrap: create venv, install deps, run doctor.
# Usage:
#   bash scripts/bootstrap.sh

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip
python -m pip install -r requirements.txt
python -m scripts.doctor

echo
echo "OK: environment ready"
