#!/bin/bash
# mac_ostanovka.sh — погасить копии на Mac. Запускать НА MAC, ПОСЛЕДНИМ.
#
# Пока этот шаг не сделан, пишут двое и журналы разъезжаются.
# Но если сделать его раньше времени, писателей станет ноль — а это хуже:
# двое пишут расходящееся, ноль не пишет ничего. Поэтому скрипт сам
# спрашивает VPS о здоровье и гасит Mac только по PASS.
set -uo pipefail
SERVER="${SERVER:-}"
UDAL="${UDAL:-/root/research-24x7/by-bot}"
KLYUCH="${KLYUCH:-$HOME/.ssh/by-bot}"
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"

[ -n "$SERVER" ] || { echo "НЕ ЗАДАН СЕРВЕР: SERVER=root@<ip> bash research_lab/mac_ostanovka.sh"; exit 2; }
SSH_OPT=(-o StrictHostKeyChecking=accept-new); [ -f "$KLYUCH" ] && SSH_OPT+=(-i "$KLYUCH")

echo "== спрашиваю VPS о здоровье =="
if ! ssh "${SSH_OPT[@]}" "$SERVER" "cd '$UDAL' && bash research_lab/vps_zdorovye.sh"; then
  echo
  echo "СТОП: VPS не здоров. Mac не гашу — иначе писателей станет ноль."
  exit 1
fi

echo
echo "== гашу копии на Mac =="
for m in "yadro.py --epoha ETS2M" "ten_sila.py" "fabrika.py --demon"; do
  k=$(pgrep -fc -- "$m" 2>/dev/null || echo 0)
  if [ "$k" -gt 0 ]; then pkill -f -- "$m" && echo "  погашено: $m ($k шт)"
  else echo "  уже не работает: $m"; fi
done
sleep 3
echo
echo "== проверка: на Mac писателей быть не должно =="
ost=0
for m in "yadro.py --epoha ETS2M" "ten_sila.py" "fabrika.py --demon"; do
  k=$(pgrep -fc -- "$m" 2>/dev/null || echo 0); ost=$((ost+k))
  printf "  %-26s %s\n" "$m" "$k"
done

{ echo "перенесено на research-VPS $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "сервер: $SERVER:$UDAL"
  echo "тени ETS2S и ATT1 остаются на Mac: другой контур, ими занимается Codex"
} > research_lab/data/PERENESENO_NA_VPS.txt

echo
if [ "$ost" -eq 0 ]; then
  echo "ИТОГ: PASS — на Mac ноль, на VPS по одному. Дублей писателей нет."
  echo "Отметка: research_lab/data/PERENESENO_NA_VPS.txt"
  exit 0
fi
echo "ИТОГ: FAIL — на Mac осталось $ost. Погасите вручную."
exit 1
