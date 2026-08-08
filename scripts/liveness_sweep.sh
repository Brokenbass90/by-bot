#!/usr/bin/env bash
# ПРОБА ЖИВОСТИ ПО ВСЕМ СТРАТЕГИЯМ — таблица «на что обратить внимание»
#
#     nohup bash scripts/liveness_sweep.sh > logs/liveness.log 2>&1 &
#     ...потом:   cat runtime/liveness_table.txt
#
# Отвечает на вопрос владельца «может ли ИИ собрать таблицу того, на что
# обратить внимание». Может, но ИИ для этого не нужен: «какое условие
# никогда не выполняется» — детерминированная трассировка, а не язык.
# Языковая модель здесь ничего не добавит и может соврать.
#
# Что делает: гоняет research_lab/strategy_liveness_probe.py по каждой
# стратегии из strategies/ на двух символах и сводит в таблицу:
#
#   ЖИВАЯ    даёт сигналы — можно свипать параметрами
#   МЁРТВАЯ  ноль сигналов на обоих символах — сначала чинить, потом свипать
#   ОШИБКА   падает с исключением
#   ПРОПУСК  нет подходящего класса или интерфейса
#
# Каждая МЁРТВАЯ разбирается вручную пробой: она печатает точки выхода
# и недостижимый код. Уже разобрано так:
#   sloped_break_retest_v1     баг единиц: expire_ts в мс + секунды
#   alt_support_reclaim_v1     дефолтный ALLOWLIST = один BCHUSDT
#   sloped_resistance_choch_v1 конъюнкция из шести условий не проходит

set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime logs

# На macOS нет GNU `timeout` — это ошибка №1 из списка граблей проекта
# («160 прогонов, код 127, ноль минут»). Ищем доступный вариант, иначе
# работаем без ограничения времени, но НЕ молча.
if command -v timeout >/dev/null 2>&1; then TO="timeout 180"
elif command -v gtimeout >/dev/null 2>&1; then TO="gtimeout 180"
else TO=""; echo "ВНИМАНИЕ: ни timeout, ни gtimeout не найдены — работаю без ограничения времени"; fi

SYMS="${SYMS:-SOLUSDT ADAUSDT}"
BARS="${BARS:-20000}"
OUT=runtime/liveness_table.txt
: > "$OUT"

printf "%-38s %8s %8s  %s\n" "стратегия" "SOL" "ADA" "вердикт" | tee -a "$OUT"
printf "%s\n" "----------------------------------------------------------------------" | tee -a "$OUT"

for f in strategies/*.py; do
  name=$(basename "$f" .py)
  case "$name" in __*|*_live|signals|live_kline_utils) continue;; esac
  n1=""; n2=""
  for sym in $SYMS; do
    raw=$($TO python3 research_lab/strategy_liveness_probe.py "$name" "$sym" "$BARS" 2>&1)
    out=$(printf "%s" "$raw" | grep -m1 "СИГНАЛОВ:" | awk '{print $2}')
    if [ -z "$out" ]; then
      # не молчим о причине: пишем первую строку ошибки рядом с таблицей
      printf "%s | %s | %s\n" "$name" "$sym" "$(printf "%s" "$raw" | tail -3 | tr "\n" " " | cut -c1-160)" >> runtime/liveness_errors.txt
    fi
    [ -z "$out" ] && out="-"
    if [ -z "$n1" ]; then n1="$out"; else n2="$out"; fi
  done
  if [ "$n1" = "-" ] && [ "$n2" = "-" ]; then verdict="ПРОПУСК/ОШИБКА"
  elif [ "${n1:-0}" = "0" ] && [ "${n2:-0}" = "0" ]; then verdict="МЁРТВАЯ — разбирать пробой"
  else verdict="живая"
  fi
  printf "%-38s %8s %8s  %s\n" "$name" "$n1" "$n2" "$verdict" | tee -a "$OUT"
done

echo | tee -a "$OUT"
echo "МЁРТВЫЕ разбирать так:" | tee -a "$OUT"
echo "    python3 research_lab/strategy_liveness_probe.py <имя> SOLUSDT 30000" | tee -a "$OUT"
echo "Свип параметров по МЁРТВОЙ ноге бессмысленен: даст нули при любых настройках." | tee -a "$OUT"
touch logs/liveness.done
