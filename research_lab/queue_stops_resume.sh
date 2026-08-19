#!/bin/bash
# НОЧЬ: контроль случайным входом по всем ногам с ШИРОКИМ стопом.
#
# Прошлый ночной прогон гонял ×6 в шорт и ×4 в лонг, но многие ноги
# настроены на очень узкий стоп (HZBO1 sl_atr_mult=0.50, у ACB1 и ARS1
# плечо 93). Для них ×6 всё равно оставляет плечо выше 20, и издержки
# съедают сигнал раньше, чем мы его увидим.
#
# Здесь стоп ×12 — чтобы у самых узких ног плечо упало до нормального,
# и стало видно, есть ли под издержками сигнал вообще.
# Значение объявлено ДО прогона и не подбирается.
#
# Запускать: nohup ./research_lab/queue_stops.sh &
cd "$(dirname "$0")/.."
L=research_lab/controls_wide.log
TO=""
command -v timeout  >/dev/null 2>&1 && TO="timeout 2400"
command -v gtimeout >/dev/null 2>&1 && TO="gtimeout 2400"
go () {
  echo "=== $(date -u +%F\ %H:%M) $3 $4 x$5 $7" >> $L
  nice -n 15 $TO python3 research_lab/random_control.py \
     "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" 2>&1 | grep -v "^\.\.\." >> $L
}
echo "=== $(date -u +%F\ %H:%M) встречные ноги" >> $L
echo "=== НОЧЬ ЗАВЕРШЕНА $(date -u)" >> $L
go micro_scalper_breakout_v1 MicroScalperBreakoutV1Strategy MSBRK long  12.0 336 "флет+" 0
go micro_scalper_v1 MicroScalperV1Strategy MSCALP short 12.0 336 "флет-" 0
go micro_scalper_v1 MicroScalperV1Strategy MSCALP long  12.0 336 "флет+" 0
go pump_fade_smart_v1 PumpFadeSmartV1Strategy PFS1 short 12.0 336 "флет-" 4
go pump_fade_smart_v1 PumpFadeSmartV1Strategy PFS1 long  12.0 336 "флет+" 4
go pump_fade_v2 PumpFadeV2Strategy PF2 short 12.0 336 "флет-" 0
go pump_fade_v2 PumpFadeV2Strategy PF2 long  12.0 336 "флет+" 0
go pump_fade_v4r PumpFadeV4RStrategy PF short 12.0 336 "флет-" 0
go pump_fade_v4r PumpFadeV4RStrategy PF long  12.0 336 "флет+" 0
go pump_momentum_v1 PumpMomentumV1Strategy PM short 12.0 336 "флет-" 0
go pump_momentum_v1 PumpMomentumV1Strategy PM long  12.0 336 "флет+" 0
go scalper_bounce_v2 ScalperBounceV2Strategy SB2 short 12.0 336 "флет-" 2
go scalper_bounce_v2 ScalperBounceV2Strategy SB2 long  12.0 336 "флет+" 2
go scalper_breakout_v2 ScalperBreakoutV2Strategy SBR2 short 12.0 336 "флет-" 4
go scalper_breakout_v2 ScalperBreakoutV2Strategy SBR2 long  12.0 336 "флет+" 4
go scalper_classic_v1 ScalperClassicV1Strategy SC1 short 12.0 336 "флет-" 1
go scalper_classic_v1 ScalperClassicV1Strategy SC1 long  12.0 336 "флет+" 1
go scalper_sweep_v2 ScalperSweepV2Strategy SS2 short 12.0 336 "флет-" 3
go scalper_sweep_v2 ScalperSweepV2Strategy SS2 long  12.0 336 "флет+" 3
go sloped_break_retest_v1 SlopedBreakRetestV1Strategy SBR1 short 12.0 336 "флет-" 0
go sloped_break_retest_v1 SlopedBreakRetestV1Strategy SBR1 long  12.0 336 "флет+" 0
go sloped_break_retest_v2 SlopedBreakRetestV2Strategy SLBR2 short 12.0 336 "флет-" 0
go sloped_break_retest_v2 SlopedBreakRetestV2Strategy SLBR2 long  12.0 336 "флет+" 0
go sloped_resistance_choch_v1 SlopedResistanceChochV1Strategy SRC1 short 12.0 336 "флет-" 0
go sloped_resistance_choch_v1 SlopedResistanceChochV1Strategy SRC1 long  12.0 336 "флет+" 0
go smart_grid SmartGridStrategy SG short 12.0 336 "флет-" 0
go smart_grid SmartGridStrategy SG long  12.0 336 "флет+" 0
echo "=== $(date -u +%F\ %H:%M) встречные ноги" >> $L
nice -n 15 python3 research_lab/antileg.py >> $L 2>&1
echo "=== ДОГОН ЗАВЕРШЁН $(date -u)" >> $L
