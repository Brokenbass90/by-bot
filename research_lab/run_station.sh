#!/bin/bash
# Запуск research-station на Mac: держит комп бодрым + авто-перезапуск (резюмится через чекпоинт).
# Использование: bash research_lab/run_station.sh <run_id> [station_file.py]
# Пример: bash research_lab/run_station.sh sloped_v1 station_sloped_v1.py
cd "$(dirname "$0")/.."
RUN_ID="${1:-station_$(date +%Y%m%d)}"
STATION="${2:-search_station.py}"
case "${STATION}" in
  */*|*..*|*.py.py)
    echo "invalid station file: ${STATION}" >&2
    exit 2
    ;;
  *.py) ;;
  *)
    echo "invalid station file: ${STATION}" >&2
    exit 2
    ;;
esac
if [[ ! -f "research_lab/${STATION}" ]]; then
  echo "station file not found: research_lab/${STATION}" >&2
  exit 2
fi
LOG="research_lab/results/${RUN_ID}.log"
mkdir -p research_lab/results
echo "station start ${RUN_ID} $(date -u)" | tee -a "$LOG"
# держим Mac бодрым до 14 дней (caffeinate); фон
caffeinate -dimsu -t 1209600 &
CAF=$!
# авто-перезапуск: если процесс упал/комп проснулся — станция резюмится с чекпоинта
while true; do
  PYTHONPATH=. python3 "research_lab/${STATION}" "$RUN_ID" >> "$LOG" 2>&1
  RC=$?
  if grep -q "ГОТОВО" "$LOG"; then echo "done $(date -u)" | tee -a "$LOG"; break; fi
  echo "restart after exit=$RC $(date -u)" | tee -a "$LOG"
  sleep 15
done
kill $CAF 2>/dev/null
