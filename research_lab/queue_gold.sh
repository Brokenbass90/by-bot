#!/bin/bash
# Золото: единственный инструмент, 14 месяцев. Двух окон нет, поэтому
# единственная честная проверка — контроль случайным входом.
# На часах сигналов слишком мало, поэтому идём по пятиминуткам.
# Запускать ПОСЛЕ ночных контролей: nohup ./research_lab/queue_gold.sh &
cd "$(dirname "$0")/.."
while pgrep -f "random_control.py" > /dev/null 2>&1; do sleep 60; done
L=research_lab/gold.log
: > $L
go () {
  echo "=== $(date -u +%F\ %H:%M) $3 $4 x$5 держ $6" >> $L
  nice -n 15 python3 research_lab/random_control.py "$1" "$2" "$3" "$4" "$5" "$6" "любой" "$7" \
      research_lab/data/gold_m5 research_lab/data/h1/BTCUSDT.npz 2>&1 | grep -v "^\.\.\." >> $L
}
for S in short long; do
  go alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1 $S 6.0 336 8
  go alt_support_reclaim_v1 AltSupportReclaimV1Strategy ASR1 $S 4.0 168 6
  go alt_range_scalp_v1     AltRangeScalpV1Strategy     ARS1 $S 4.0 168 4
  go spike_fade_v3          SpikeFadeV3Strategy         SF3  $S 4.0 336 0
done
echo "=== ЗОЛОТО ЗАВЕРШЕНО $(date -u)" >> $L
