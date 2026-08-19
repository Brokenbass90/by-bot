#!/bin/bash
cd "$(dirname "$0")/.."
echo "=== $(date -u +%F\ %H:%M) старт: горизонтальные уровни" > research_lab/levels.log
nice -n 15 python3 research_lab/levels_experiment.py >> research_lab/levels.log 2>&1
echo "=== готово $(date -u)" >> research_lab/levels.log
