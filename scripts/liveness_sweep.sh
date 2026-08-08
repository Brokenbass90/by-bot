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
PROBE_TIMEOUT_SEC="${LIVENESS_PROBE_TIMEOUT_SEC:-180}"
if command -v timeout >/dev/null 2>&1; then TO="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TO="gtimeout"
elif command -v perl >/dev/null 2>&1; then TO="perl_alarm"
else TO=""; echo "ОШИБКА: нет timeout/gtimeout/perl; безопасный полный свип невозможен" >&2; exit 2; fi

run_probe() {
  if [ "$TO" = "perl_alarm" ]; then
    /usr/bin/perl -e 'alarm shift; exec @ARGV' "$PROBE_TIMEOUT_SEC" \
      python3 research_lab/strategy_liveness_probe.py "$@"
  else
    "$TO" "$PROBE_TIMEOUT_SEC" \
      python3 research_lab/strategy_liveness_probe.py "$@"
  fi
}

SYMS="${SYMS:-SOLUSDT ADAUSDT}"
BARS="${BARS:-20000}"
OUT=runtime/liveness_table.txt
TMP_OUT="${OUT}.tmp.$$"
ERR_OUT=runtime/liveness_errors.txt
TMP_ERR="${ERR_OUT}.tmp.$$"
STATUS=runtime/liveness_status.json
trap 'rm -f "$TMP_OUT" "$TMP_ERR"' EXIT INT TERM HUP
: > "$TMP_OUT"
: > "$TMP_ERR"

printf "%-38s %8s %8s  %s\n" "стратегия" "SOL" "ADA" "вердикт" | tee -a "$TMP_OUT"
printf "%s\n" "----------------------------------------------------------------------" | tee -a "$TMP_OUT"

python3 - "$STATUS" "$PROBE_TIMEOUT_SEC" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "schema_id": "strategy_liveness_status_v1",
    "state": "running",
    "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "probe_timeout_sec": int(sys.argv[2]),
    "complete": False,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

total=0
live=0
dead=0
skipped=0
timeouts=0

for f in strategies/*.py; do
  name=$(basename "$f" .py)
  case "$name" in __*|*_live|signals|live_kline_utils) continue;; esac
  total=$((total + 1))
  n1=""; n2=""
  for sym in $SYMS; do
    raw=$(run_probe "$name" "$sym" "$BARS" 2>&1)
    rc=$?
    out=$(printf "%s" "$raw" | grep -m1 "СИГНАЛОВ:" | awk '{print $2}')
    if [ -z "$out" ]; then
      # не молчим о причине: пишем первую строку ошибки рядом с таблицей
      [ "$rc" -eq 142 ] && timeouts=$((timeouts + 1))
      printf "%s | %s | rc=%s | %s\n" "$name" "$sym" "$rc" "$(printf "%s" "$raw" | tail -3 | tr "\n" " " | cut -c1-160)" >> "$TMP_ERR"
    fi
    [ -z "$out" ] && out="-"
    if [ -z "$n1" ]; then n1="$out"; else n2="$out"; fi
  done
  if [ "$n1" = "-" ] && [ "$n2" = "-" ]; then verdict="ПРОПУСК/ОШИБКА"; skipped=$((skipped + 1))
  elif [ "${n1:-0}" = "0" ] && [ "${n2:-0}" = "0" ]; then verdict="МЁРТВАЯ — разбирать пробой"; dead=$((dead + 1))
  else verdict="живая"; live=$((live + 1))
  fi
  printf "%-38s %8s %8s  %s\n" "$name" "$n1" "$n2" "$verdict" | tee -a "$TMP_OUT"
done

echo | tee -a "$TMP_OUT"
echo "МЁРТВЫЕ разбирать так:" | tee -a "$TMP_OUT"
echo "    python3 research_lab/strategy_liveness_probe.py <имя> SOLUSDT 30000" | tee -a "$TMP_OUT"
echo "Свип параметров по МЁРТВОЙ ноге бессмысленен: даст нули при любых настройках." | tee -a "$TMP_OUT"
echo "LIVENESS_SWEEP_COMPLETE total=$total live=$live dead=$dead skipped=$skipped timeouts=$timeouts" | tee -a "$TMP_OUT"

# Не публикуем частичную таблицу: только полностью завершённый sweep заменяет
# предыдущую authoritative-копию.
mv "$TMP_OUT" "$OUT"
mv "$TMP_ERR" "$ERR_OUT"
python3 - "$STATUS" "$total" "$live" "$dead" "$skipped" "$timeouts" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "schema_id": "strategy_liveness_status_v1",
    "state": "complete",
    "completed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "complete": True,
    "total": int(sys.argv[2]),
    "live": int(sys.argv[3]),
    "dead_candidates": int(sys.argv[4]),
    "skipped_or_error": int(sys.argv[5]),
    "probe_timeouts": int(sys.argv[6]),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
touch logs/liveness.done
