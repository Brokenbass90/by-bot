#!/bin/bash
# Две ноги, прошедшие контроль на обоих окнах: ATT1 шорт во флете вниз
# и SBR1 лонг во флете вверх. Вместе они покрывают 51% времени.
# Сначала проверка концентрации SBR1, потом сборка портфеля.
cd "$(dirname "$0")/.."
L=research_lab/two_legs.log
: > $L
echo "=== $(date -u +%F\ %H:%M) концентрация SBR1 лонг флет+" >> $L
nice -n 15 python3 research_lab/concentration.py sloped_break_retest_v1 SlopedBreakRetestV1Strategy SBR1 long 4.0 168 "флет+" 0 2>&1 | grep -v "^\.\.\." >> $L
echo "=== $(date -u +%F\ %H:%M) портфель из двух ног" >> $L
nice -n 15 python3 research_lab/orchestrator.py --rebuild >> $L 2>&1
echo "=== ГОТОВО $(date -u)" >> $L
