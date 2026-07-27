#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
"${REPO_ROOT}/scripts/setup_massive_stocks_basic_env.sh"

echo
read -r -p "Нажмите Enter, чтобы закрыть окно..."
