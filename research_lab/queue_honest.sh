#!/bin/bash
# ЧЕСТНАЯ ОЧЕРЕДЬ: то же самое, но с паузой между сделками, приведённой
# к единицам вызова (штатное значение / 12 на часовых данных).
#
# Замер на ATT1: 196 сигналов при паузе 96, 349 при паузе 8. Все прежние
# прогоны недосчитывали около 44% сделок, и часть «нехватки статистики»
# была создана единицами измерения, а не рынком.
#
# Сначала дожидается оркестратора, если он ещё считает, чтобы не драться
# за процессор. Потом перепрогоняет ноги. Потом пересобирает оркестратор
# на исправленных сигналах.
#
# Запускать: nohup ./research_lab/queue_honest.sh &
cd "$(dirname "$0")/.."
L=research_lab/queue_honest.log
: > $L

# ждём оркестратор, если он живой
if pgrep -f "orchestrator.py" > /dev/null 2>&1; then
  echo "=== $(date -u +%F\ %H:%M) жду оркестратор на старом кэше" >> $L
  while pgrep -f "orchestrator.py" > /dev/null 2>&1; do sleep 30; done
  echo "=== $(date -u +%F\ %H:%M) оркестратор закончил, забираю его итог" >> $L
  sed -n '/окно 2024-03/,$p' research_lab/orch.log >> $L
  cp research_lab/orch_signals.json research_lab/orch_signals_old_cooldown.json 2>/dev/null
fi

run () {
  echo "=== $(date -u +%F\ %H:%M) старт $4 (пауза $5)" >> $L
  nice -n 15 python3 research_lab/research_machine.py \
      --strategy "$1" --cls "$2" --prefix "$3" \
      --data research_lab/data/h1 --tag "$4" --root . --cooldown "$5" \
      > "research_lab/rm_$4.log" 2>&1
  echo "=== $(date -u +%F\ %H:%M) готово $4" >> $L
  sed -n '/ОТСЕВ/,$p' "research_lab/rm_$4.log" >> $L
}
run alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1  att1_h   8
run alt_support_reclaim_v1 AltSupportReclaimV1Strategy ASR1  asr1_h   6
run elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2  ets2_h   3
run alt_horizontal_break_v1 AltHorizontalBreakV1Strategy HZBO1 hzbo1_h 5
run alt_resistance_fade_v1 AltResistanceFadeV1Strategy  ARF1  arf1_h  4

echo "=== $(date -u +%F\ %H:%M) пересборка оркестратора на честных сигналах" >> $L
nice -n 15 python3 research_lab/orchestrator.py --rebuild >> $L 2>&1
echo "=== ЧЕСТНАЯ ОЧЕРЕДЬ ЗАВЕРШЕНА $(date -u)" >> $L
