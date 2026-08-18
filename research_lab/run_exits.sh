#!/bin/bash
# Объявленный эксперимент: безубыток и трейлинг из живого кода ATT1.
# Запускать ПОСЛЕ перепрогона: nohup ./research_lab/run_exits.sh &
cd "$(dirname "$0")/.."
while pgrep -f "research_machine.py" > /dev/null 2>&1; do sleep 30; done
echo "=== $(date -u +%F\ %H:%M) старт эксперимента с выходами" > research_lab/exits.log
nice -n 15 python3 research_lab/exits_experiment.py >> research_lab/exits.log 2>&1
echo "=== $(date -u +%F\ %H:%M) готово" >> research_lab/exits.log
