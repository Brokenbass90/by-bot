#!/bin/bash
# Запуск research-station на Mac: держит комп бодрым + авто-перезапуск (резюмится через чекпоинт).
# Использование: bash research_lab/run_station.sh <run_id>
cd "$(dirname "$0")/.."
RUN_ID="${1:-station_$(date +%Y%m%d)}"
LOG="research_lab/results/${RUN_ID}.log"
mkdir -p research_lab/results
echo "station start ${RUN_ID} $(date -u)" | tee -a "$LOG"
# держим Mac бодрым до 14 дней (caffeinate); фон
caffeinate -dimsu -t 1209600 &
CAF=$!
# авто-перезапуск: если процесс упал/комп проснулся — станция резюмится с чекпоинта
while true; do
  PYTHONPATH=. python3 research_lab/search_station.py "$RUN_ID" >> "$LOG" 2>&1
  RC=$?
  if grep -q "ГОТОВО" "$LOG"; then echo "done $(date -u)" | tee -a "$LOG"; break; fi
  echo "restart after exit=$RC $(date -u)" | tee -a "$LOG"
  sleep 15
done
kill $CAF 2>/dev/null
