#!/bin/bash
# perenos_na_vps.sh — перевозит на VPS ТОЛЬКО состояние исследования.
#
# ЗАЧЕМ. Всё, что копится (когорта ETS2M, тень SILA, суточный Polymarket),
# идёт ровно столько, сколько включён Mac. За неделю трое суток из семи
# проект не существовал. VPS работает всегда.
#
# БЕЗОПАСНОСТЬ. Список файлов БЕЛЫЙ, а не чёрный: везём перечисленное
# поимённо и ничего больше. Конфиги, .env, ключи, signal_copy сюда попасть
# не могут по построению, даже если кто-то их туда положит.
#
# Код НЕ везём: он приезжает git-ом из ветки research/fabrika-v1.
# Везём только то, чего в git нет.
#
#   bash research_lab/perenos_na_vps.sh --proverka   сухой прогон, ничего не пишет
#   bash research_lab/perenos_na_vps.sh --vezti      собственно перенос
set -euo pipefail

SERVER="${SERVER:-root@64.226.73.119}"
UDAL="${UDAL:-/root/research-24x7/by-bot}"
KOREN="$(cd "$(dirname "$0")/.." && pwd)"

# ── БЕЛЫЙ СПИСОК. Только состояние, которого нет в git. ───────────────
VEZYOM=(
  "research_lab/data/yadro/"                 # когорта ETS2M: epoha, входы, исходы
  "research_lab/data/ten_SILA.jsonl"         # решения тени
  "research_lab/data/ten_SILA_sostoyanie.json"  # ЗАМОРОЖЕННЫЙ момент старта
  "research_lab/data/ten_SILA_ceny.json"     # кэш цен тени
  "research_lab/data/poly/istoriya/"         # история Polymarket, 47 МБ
  "research_lab/data/poly/otobrano.json"     # отобранные рынки
  "research_lab/data/pit_daily/"             # дневные цены крипты, 78 МБ
)
# НЕ везём намеренно: data/poly/katalog (5.7 ГБ, нужен только для пересборки
# сопоставления), configs, .env, signal_copy, ключи — ничего из этого
# в списке нет и быть не может.

rezhim="${1:---proverka}"

echo "источник : $KOREN"
echo "цель     : $SERVER:$UDAL"
echo "режим    : $rezhim"
echo

vsego=0
for p in "${VEZYOM[@]}"; do
  if [ ! -e "$KOREN/$p" ]; then
    echo "  ОТСУТСТВУЕТ: $p"; continue
  fi
  r=$(du -sh "$KOREN/$p" | cut -f1)
  n=$(find "$KOREN/$p" -type f 2>/dev/null | wc -l | tr -d ' ')
  printf "  %-46s %8s  файлов %s\n" "$p" "$r" "$n"
  vsego=$((vsego+1))
done
echo
echo "позиций к переносу: $vsego"

if [ "$rezhim" != "--vezti" ]; then
  echo
  echo "Это сухой прогон. Ничего не отправлено."
  echo "Перенести:  bash research_lab/perenos_na_vps.sh --vezti"
  exit 0
fi

echo "готовлю каталог на сервере…"
ssh -o StrictHostKeyChecking=accept-new "$SERVER" "mkdir -p '$UDAL/research_lab/data'"

for p in "${VEZYOM[@]}"; do
  [ -e "$KOREN/$p" ] || continue
  echo "→ $p"
  rsync -az --info=stats1 --relative "$KOREN/./$p" "$SERVER:$UDAL/"
done

echo
echo "перенос закончен. Дальше — research_lab/vps_zapusk.sh НА СЕРВЕРЕ."
