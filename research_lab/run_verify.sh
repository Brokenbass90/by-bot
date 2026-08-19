#!/bin/bash
cd "$(dirname "$0")/.."
echo "=== $(date -u +%F\ %H:%M) проверка живой конфигурации" > research_lab/verify.log
nice -n 15 python3 research_lab/verify_live_config.py >> research_lab/verify.log 2>&1
echo "=== готово $(date -u)" >> research_lab/verify.log
