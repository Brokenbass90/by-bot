#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_PATH="${REPO_ROOT}/configs/massive_stocks_local.env"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

echo "Massive Stocks Basic: безопасная локальная настройка"
echo "Ключ не будет показан и не попадёт в Git."
read -r -s -p "Вставьте API key из Massive Dashboard и нажмите Enter: " API_KEY
echo

if [[ -z "${API_KEY}" ]]; then
  echo "Пустой ключ. Ничего не изменено." >&2
  exit 2
fi
if [[ "${API_KEY}" == *$'\n'* || "${API_KEY}" == *$'\r'* ]]; then
  echo "Ключ содержит перевод строки. Ничего не изменено." >&2
  exit 2
fi

umask 077
printf 'MASSIVE_API_KEY=%s\n' "${API_KEY}" > "${ENV_PATH}"
chmod 600 "${ENV_PATH}"
unset API_KEY

echo "Локальный env сохранён с правами 600. Проверяю три Basic endpoint..."
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/verify_massive_stocks_basic.py" \
  --env-file "${ENV_PATH}" \
  --output-json "${REPO_ROOT}/runtime/massive_stocks_basic_audit.json"

echo
echo "Готово: runtime/massive_stocks_basic_audit.json"
