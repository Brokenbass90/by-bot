#!/bin/bash
# Контроль случайным входом: сколько наши ноги дают СВЕРХ случайной
# сделки с той же геометрией в том же месяце по той же монете.
# Запускать: nohup ./research_lab/run_controls.sh &
cd "$(dirname "$0")/.."
L=research_lab/controls.log
: > $L
go () {
  echo "=== $(date -u +%F\ %H:%M) $1" >> $L
  nice -n 15 python3 research_lab/random_control.py "$@" 2>&1 | grep -v "^\.\.\." >> $L
}
go sloped_break_retest_v1  SlopedBreakRetestV1Strategy  SBR1 short 1.0 336 "флет-" 0
go alt_trendline_touch_v1  AltTrendlineTouchV1Strategy  ATT1 short 6.0 336 "флет-" 8
go alt_trendline_touch_v1  AltTrendlineTouchV1Strategy  ATT1 short 6.0 336 "любой" 8
go micro_scalper_breakout_v1 MicroScalperBreakoutV1Strategy MSBRK short 2.0 336 "флет+" 0
go alt_sloped_momentum_v1  AltSlopedMomentumV1Strategy  ASM1 long  4.0 168 "растёт" 6
echo "=== КОНТРОЛИ ЗАВЕРШЕНЫ $(date -u)" >> $L
