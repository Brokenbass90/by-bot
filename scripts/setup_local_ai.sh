#!/usr/bin/env bash
# Установка локального ИИ и исследовательских зависимостей.
#
# ЗАПУСКАТЬ У СЕБЯ (мак или сервер), не в песочнице.
#   bash scripts/setup_local_ai.sh
#
# Ничего не трогает в live-боте: ставится только Ollama, модель
# и research-зависимости в отдельное окружение.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 1. Ollama ==="
if command -v ollama >/dev/null 2>&1; then
    echo "уже установлена: $(ollama --version 2>/dev/null || echo ok)"
else
    case "$(uname -s)" in
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                brew install ollama
                echo "запустить сервис: brew services start ollama"
            else
                echo "Homebrew не найден. Скачайте вручную: https://ollama.com/download"
                exit 1
            fi
            ;;
        Linux)
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        *)
            echo "неизвестная ОС, поставьте вручную: https://ollama.com/download"
            exit 1
            ;;
    esac
fi

echo
echo "=== 2. Модель ==="
# qwen3:8b — компромисс: осмысленный поиск, влезает в 8-16 ГБ,
# идёт и на CPU (медленно, но для ночных задач достаточно).
# Если есть 24 ГБ VRAM — заменить на qwen3-coder:30b.
MODEL="${OLLAMA_MODEL:-qwen3:8b}"
echo "тяну $MODEL (несколько ГБ, займёт время)"
ollama pull "$MODEL"

echo
echo "=== 3. Research-зависимости ==="
# Отдельным файлом, чтобы НИКОГДА не попасть в live-рантайм.
REQ="requirements-research-open-source.txt"
for pkg in "scipy>=1.11" "statsmodels>=0.14" "ruptures>=1.1"; do
    name="${pkg%%>=*}"
    grep -qi "^${name}" "$REQ" || echo "$pkg" >> "$REQ"
done
python3 -m pip install --user -r "$REQ" || \
    python3 -m pip install --break-system-packages -r "$REQ"

echo
echo "=== 4. Проверка ==="
python3 - <<'PY'
import importlib
for m in ("scipy", "statsmodels", "ruptures"):
    try:
        importlib.import_module(m)
        print(f"  {m}: ok")
    except Exception as e:
        print(f"  {m}: НЕ УСТАНОВЛЕН ({e})")
PY

echo
echo "проверка Ollama (должен ответить):"
curl -s http://localhost:11434/api/tags >/dev/null 2>&1 \
    && echo "  сервис отвечает" \
    || echo "  сервис не отвечает — запустите: ollama serve"

echo
echo "=== Готово. Дальше ==="
echo "  аудитор без модели:   python3 research_lab/ai_auditor.py"
echo "  аудитор с моделью:    python3 research_lab/ai_auditor.py --with-model"
echo "  в расписание (3 ночи): 0 3 * * * cd $(pwd) && python3 research_lab/ai_auditor.py"
