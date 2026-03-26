#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

python3 scripts/build_battle_snapshot.py "$@"
