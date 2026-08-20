#!/bin/bash
# Ордерблоки: три таймфрейма × две ширины стопа, все 137 символов.
# Сетка объявлена ДО прогона: тф 1/4/24 ч, стоп ×1 и ×4.
# Запускать: caffeinate -i nohup ./research_lab/run_ob.sh &
cd "$(dirname "$0")/.."
L=research_lab/orderblock.log
touch $L
for TF in 1 4 24; do
  for SM in 1.0 4.0; do
    if grep -q "бар = $TF ч, стоп ×$SM" $L 2>/dev/null; then continue; fi
    echo "=== $(date -u +%F\ %H:%M) тф $TF ч, стоп ×$SM" >> $L
    nice -n 15 python3 research_lab/orderblock.py --tf $TF --stopmult $SM 2>&1 | grep -v "^\.\.\." >> $L
  done
done
echo "=== ОРДЕРБЛОКИ ЗАВЕРШЕНЫ $(date -u)" >> $L
