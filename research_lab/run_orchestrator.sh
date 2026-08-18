#!/bin/bash
# Сборка сигналов четырёх ног и проверка диспетчера.
# Первый прогон долгий (генерируются сигналы), дальше читает кэш мгновенно.
# Запускать: nohup ./research_lab/run_orchestrator.sh &
cd "$(dirname "$0")/.."
echo "=== $(date -u +%F\ %H:%M) старт оркестратора" > research_lab/orch.log
nice -n 15 python3 research_lab/orchestrator.py --rebuild >> research_lab/orch.log 2>&1
echo "=== $(date -u +%F\ %H:%M) готово" >> research_lab/orch.log
