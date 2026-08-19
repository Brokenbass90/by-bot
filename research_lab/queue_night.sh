#!/bin/bash
# Ночная очередь исследований. Запускается НА МАШИНЕ ВЛАДЕЛЬЦА, чтобы
# пережить ночь: облачный контейнер Claude засыпает вместе с сессией.
# nice 15 — не мешать Кодексу и системе.
cd "$(dirname "$0")/.."
L=research_lab/queue_night.log
run () {
  echo "=== $(date -u +%F\ %H:%M) старт $4" >> $L
  nice -n 15 python3 research_lab/research_machine.py \
      --strategy "$1" --cls "$2" --prefix "$3" \
      --data research_lab/data/h1 --tag "$4" --root . \
      > "research_lab/rm_$4.log" 2>&1
  echo "=== $(date -u +%F\ %H:%M) готово $4" >> $L
  sed -n '/ОТСЕВ/,$p' "research_lab/rm_$4.log" >> $L
}
run alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1 att1_night
run elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2 ets2_night
run alt_resistance_fade_v1 AltResistanceFadeV1Strategy ARF1 arf1_night
echo "=== ОЧЕРЕДЬ ЗАВЕРШЕНА $(date -u)" >> $L
