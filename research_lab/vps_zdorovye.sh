#!/bin/bash
# vps_zdorovye.sh — здоров ли контур исследования. ТОЛЬКО ЧТЕНИЕ.
# Код возврата: 0 — PASS, 1 — FAIL.
set -uo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"

vsego=0; upalo=0
ok ()  { printf "  [ PASS ] %-30s %s\n" "$1" "$2"; vsego=$((vsego+1)); }
bad () { printf "  [ FAIL ] %-30s %s\n" "$1" "$2"; vsego=$((vsego+1)); upalo=$((upalo+1)); }

echo "ЗДОРОВЬЕ ИССЛЕДОВАНИЯ  $(hostname)  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo
echo "СЛУЖБЫ"
for s in research-yadro_ETS2M research-ten_SILA research-fabrika; do
  if ! systemctl list-unit-files "$s.service" >/dev/null 2>&1 || \
     [ -z "$(systemctl list-unit-files --no-legend "$s.service" 2>/dev/null)" ]; then
    bad "$s" "юнита нет — не выполнен vps_ustanovka.sh"; continue
  fi
  a=$(systemctl is-active "$s" 2>/dev/null || true)
  e=$(systemctl is-enabled "$s" 2>/dev/null || true)
  [ "$a" = "active" ] && ok "$s активна" "$a, автозапуск $e" || bad "$s активна" "$a"
  [ "$e" = "enabled" ] || bad "$s автозапуск" "$e — не переживёт перезагрузку"
done

echo
echo "ПИСАТЕЛИ (обязано быть ровно по одному)"
for m in "yadro.py --epoha ETS2M" "ten_sila.py" "fabrika.py --demon"; do
  k=$(pgrep -fc -- "$m" 2>/dev/null || echo 0)
  if [ "$k" -eq 1 ]; then ok "$m" "1"
  elif [ "$k" -eq 0 ]; then bad "$m" "0 — никто не пишет"
  else bad "$m" "$k — ДУБЛЬ, журналы разъедутся"; fi
done

echo
echo "СВЕЖЕСТЬ"
svezh () {                       # $1 файл, $2 предел минут, $3 подпись
  if [ ! -e "$1" ]; then bad "$3" "файла нет: $1"; return; fi
  local m=$(( ( $(date +%s) - $(stat -c %Y "$1") ) / 60 ))
  [ "$m" -le "$2" ] && ok "$3" "${m} мин назад (предел ${2})" \
                    || bad "$3" "${m} мин назад, предел ${2} — процесс молчит"
}
svezh research_lab/data/vps_yadro_ETS2M.log 90  "лог ETS2M (цикл 60 мин)"
svezh research_lab/data/vps_fabrika.log     45  "лог фабрики (цикл 30 мин)"
svezh research_lab/data/ten_SILA.bienie    420  "биение SILA (цикл 360 мин)"

echo
echo "СОСТОЯНИЕ ОТНОСИТЕЛЬНО ЭТАЛОНА"
if python3 research_lab/vps_sravnit.py --rezhim posle | sed 's/^/  /'; then
  vsego=$((vsego+8))
else
  vsego=$((vsego+8)); upalo=$((upalo+1))
fi

echo
echo "МАШИНА"
MA=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
[ "$MA" -ge 300 ] && ok "RAM доступно" "${MA} Mi" || bad "RAM доступно" "${MA} Mi — близко к тому, что убило прошлый сервер"
SV=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
[ "$SV" -ge 5 ] && ok "свободно на /" "${SV} G" || bad "свободно на /" "${SV} G"
if [ -r /proc/pressure/io ]; then
  V=$(awk '$1=="full"{for(i=2;i<=NF;i++) if($i ~ /^avg300=/){sub("avg300=","",$i); print $i}}' /proc/pressure/io)
  awk -v a="$V" 'BEGIN{exit !(a<2)}' && ok "io full avg300" "$V %" || bad "io full avg300" "$V % — машина стоит"
fi

echo
echo "───────────────────────────────────────────────"
printf "проверок %s, провалов %s\n" "$vsego" "$upalo"
[ "$upalo" -eq 0 ] && { echo "ИТОГ: PASS"; exit 0; } || { echo "ИТОГ: FAIL"; exit 1; }
