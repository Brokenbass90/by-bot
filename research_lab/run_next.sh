#!/bin/bash
# 1) горизонтальные уровни: не вяло ли рисуем
# 2) портфель с приоритетом и 12 слотами
cd "$(dirname "$0")/.."
./research_lab/run_levels.sh
echo "=== $(date -u +%F\ %H:%M) портфель: приоритет + 12 слотов" >> research_lab/levels.log
nice -n 15 python3 research_lab/orchestrator.py >> research_lab/levels.log 2>&1
echo "=== ВСЁ ГОТОВО $(date -u)" >> research_lab/levels.log
