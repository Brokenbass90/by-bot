#!/bin/bash
# perenos_na_vps.sh — перевозит на research-VPS ТОЛЬКО состояние исследования.
#
# ЗАЧЕМ. Всё, что копится проспективно (когорта ETS2M, решения тени SILA,
# суточный Polymarket), идёт ровно столько, сколько включён Mac. За неделю
# 25-28 сентября трое суток из семи проект не существовал.
#
# БЕЗОПАСНОСТЬ. Список БЕЛЫЙ: везём перечисленное поимённо и ничего больше.
# Конфиги, .env, ключи, signal_copy сюда попасть не могут по построению.
#
# Код приезжает git-ом из ветки research/fabrika-v1. Но состояние фабрики
# лежит в той же ветке СНИМКОМ на момент последнего коммита, а живые файлы
# уходят вперёд каждые полчаса. Поэтому ochered/verdikty/zadachi/rezultaty
# едут ещё и rsync-ом и перезаписывают то, что принёс git. Так перенос
# перестаёт зависеть от того, вспомнили ли закоммитить перед выездом.
#
#   SERVER=root@<ip> bash research_lab/perenos_na_vps.sh --proverka
#   SERVER=root@<ip> bash research_lab/perenos_na_vps.sh --vezti
set -euo pipefail

SERVER="${SERVER:-}"
UDAL="${UDAL:-/root/research-24x7/by-bot}"
KLYUCH="${KLYUCH:-$HOME/.ssh/by-bot}"
KOREN="$(cd "$(dirname "$0")/.." && pwd)"

# ── ЗАПРЕТ. Продакшн Codex. Диагноз — VPS_DIAGNOZ_2026_09_29.md. ──────
ZAPRESHCHENO="64.226.73.119"

# ── БЕЛЫЙ СПИСОК. Только состояние. ──────────────────────────────────
VEZYOM=(
  # ETS2M: когорта не имеет права начаться заново
  "research_lab/data/yadro/"
  # тень SILA: решения и ЗАМОРОЖЕННЫЙ момент старта
  "research_lab/data/ten_SILA.jsonl"
  "research_lab/data/ten_SILA_sostoyanie.json"
  "research_lab/data/ten_SILA_ceny.json"
  # канонический реестр и его история
  "research_lab/data/reestr.json"
  "research_lab/data/reestr_istoriya.jsonl"
  # фабрика: очередь, вердикты, задачи, результаты, тени, предложения
  "research_lab/fabrika/ochered.json"
  "research_lab/fabrika/verdikty.jsonl"
  "research_lab/fabrika/zadachi.json"
  "research_lab/fabrika/rezultaty/"
  "research_lab/fabrika/teni/"
  "research_lab/fabrika/predlozheniya/"
  "research_lab/fabrika/.poly_posledniy"
  # Polymarket: сопоставление собрано, пересобирать нечем
  "research_lab/data/poly/istoriya/"
  "research_lab/data/poly/otobrano.json"
  # данные, от которых зависит отпечаток и состояния очереди.
  # Без них BLOCKED_DATA разъедется с Mac и реестр перестанет совпадать.
  "research_lab/data/pit_daily/"
  "research_lab/data/basis/"
  "research_lab/data/alpaca_pit_daily_v1/bars/"
  # эталон для механической сверки на той стороне
  "research_lab/data/ETALON_PERENOSA.json"
)
# НЕ везём намеренно: data/poly/katalog (5.7 ГБ, нужен только для пересборки
# сопоставления), configs, .env, signal_copy, ключи.

# Замки, pid и биения НЕ едут никогда: чужой замок на той стороне либо
# не даст процессу подняться, либо совпадёт с чужим живым pid.
ISKLYUCHIT=( --exclude='*.pid' --exclude='*.bienie' --exclude='.zamok'
             --exclude='*.lock' --exclude='__pycache__' --exclude='.DS_Store' )

rezhim="${1:---proverka}"

if [ -z "$SERVER" ]; then
  echo "НЕ ЗАДАН СЕРВЕР."
  echo "  SERVER=root@<ip> bash research_lab/perenos_na_vps.sh $rezhim"
  exit 2
fi
case "$SERVER" in
  *"$ZAPRESHCHENO"*)
    echo "СТОП: $ZAPRESHCHENO — продакшн Codex, и он уже за пределами ресурсов."
    echo "1 ядро, 33 Mi свободной памяти, io full avg300 = 10 %."
    echo "Подробности: research_lab/VPS_DIAGNOZ_2026_09_29.md"
    exit 2 ;;
esac

echo "источник : $KOREN"
echo "цель     : $SERVER:$UDAL"
[ -f "$KLYUCH" ] && echo "ключ     : $KLYUCH" || echo "ключ     : не найден ($KLYUCH), беру из ~/.ssh/config"
echo "режим    : $rezhim"
echo

SSH_OPT=(-o StrictHostKeyChecking=accept-new)
[ -f "$KLYUCH" ] && SSH_OPT+=(-i "$KLYUCH")

vsego=0; net=0
for p in "${VEZYOM[@]}"; do
  if [ ! -e "$KOREN/$p" ]; then
    printf "  %-46s ОТСУТСТВУЕТ\n" "$p"; net=$((net+1)); continue
  fi
  r=$(du -sh "$KOREN/$p" | cut -f1)
  n=$(find "$KOREN/$p" -type f 2>/dev/null | wc -l | tr -d ' ')
  printf "  %-46s %8s  файлов %s\n" "$p" "$r" "$n"
  vsego=$((vsego+1))
done
echo
echo "позиций к переносу: $vsego   отсутствует: $net"

if [ "$rezhim" != "--vezti" ]; then
  echo
  echo "Это сухой прогон. Ничего не отправлено."
  echo "Дальше:  bash research_lab/vps_etalon.sh"
  echo "потом :  SERVER=$SERVER bash research_lab/perenos_na_vps.sh --vezti"
  exit 0
fi

# ── эталон обязателен и должен быть свежим ───────────────────────────
ET="$KOREN/research_lab/data/ETALON_PERENOSA.json"
if [ ! -f "$ET" ]; then
  echo "НЕТ ЭТАЛОНА. Сначала:  bash research_lab/vps_etalon.sh"; exit 2
fi
VOZRAST=$(python3 -c "import json,datetime,sys
d=json.load(open('$ET',encoding='utf-8'))['_snyat']
t=datetime.datetime.fromisoformat(d)
print(int((datetime.datetime.now(datetime.timezone.utc)-t).total_seconds()))")
if [ "$VOZRAST" -gt 1800 ]; then
  echo "ЭТАЛОН СТАРЫЙ: снят $((VOZRAST/60)) минут назад."
  echo "Mac продолжает писать — на той стороне сверка не сойдётся."
  echo "Пересними:  bash research_lab/vps_etalon.sh"; exit 2
fi
echo "эталон свежий: $((VOZRAST/60)) мин назад"
echo

echo "готовлю каталог на сервере…"
ssh "${SSH_OPT[@]}" "$SERVER" "mkdir -p '$UDAL/research_lab/data' '$UDAL/research_lab/fabrika'"

for p in "${VEZYOM[@]}"; do
  [ -e "$KOREN/$p" ] || continue
  echo "→ $p"
  rsync -az --info=stats1 --relative "${ISKLYUCHIT[@]}" \
        -e "ssh ${SSH_OPT[*]}" "$KOREN/./$p" "$SERVER:$UDAL/"
done

echo
echo "перевезено. Дальше НА СЕРВЕРЕ:"
echo "  cd $UDAL && bash research_lab/vps_sverka.sh"
