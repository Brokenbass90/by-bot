#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew services start ollama >/dev/null 2>&1 || true
    sleep 2
  fi
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama не отвечает на 127.0.0.1:11434."
  echo "Запустите приложение Ollama или выполните: brew services start ollama"
  read -r -p "Нажмите Enter, чтобы закрыть окно..."
  exit 1
fi

"${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/chat_with_local_ai.py"

echo
read -r -p "Нажмите Enter, чтобы закрыть окно..."
