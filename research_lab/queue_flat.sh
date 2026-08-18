#!/bin/bash
# Очередь: ФЛЕТОВАЯ семья + перепрогон двух живых ног под новую сетку режимов.
#
# С этого прогона у машины семь режимных ячеек вместо трёх:
#   любой / падает / растёт        — как было, для сравнимости со старыми логами
#   флет- / флет+                  — BTC в пределах ±2% от своей EMA200
#   тренд- / тренд+                — BTC дальше 2% от EMA200
# Порог 2% объявлен ДО прогона и не подбирался.
#
# Запускать на машине владельца: nohup ./research_lab/queue_flat.sh &
cd "$(dirname "$0")/.."
L=research_lab/queue_flat.log
: > $L
run () {
  echo "=== $(date -u +%F\ %H:%M) старт $4" >> $L
  nice -n 15 python3 research_lab/research_machine.py \
      --strategy "$1" --cls "$2" --prefix "$3" \
      --data research_lab/data/h1 --tag "$4" --root . \
      > "research_lab/rm_$4.log" 2>&1
  echo "=== $(date -u +%F\ %H:%M) готово $4" >> $L
  sed -n '/ОТСЕВ/,$p' "research_lab/rm_$4.log" >> $L
}
# --- флетовая семья
run alt_channel_bounce_v1   AltChannelBounceV1Strategy   ACB1 acb1
run alt_range_reclaim_v1    AltRangeReclaimV1Strategy    ARR1 arr1
run alt_range_scalp_v1      AltRangeScalpV1Strategy      ARS1 ars1
run alt_resistance_fade_v2  AltResistanceFadeV2Strategy  ARF2 arf2
run pump_fade_smart_v1      PumpFadeSmartV1Strategy      PFS1 pfs1
run spike_fade_v3           SpikeFadeV3Strategy          SF3  sf3
# --- перепрогон живых ног под новую сетку режимов
run alt_trendline_touch_v1  AltTrendlineTouchV1Strategy  ATT1 att1_flat
run alt_support_reclaim_v1  AltSupportReclaimV1Strategy  ASR1 asr1_flat
echo "=== ОЧЕРЕДЬ ФЛЕТ ЗАВЕРШЕНА $(date -u)" >> $L
