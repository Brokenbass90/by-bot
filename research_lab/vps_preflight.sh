#!/bin/bash
# vps_preflight.sh — годится ли машина под исследование. ТОЛЬКО ЧТЕНИЕ.
#
# Запускать НА КАНДИДАТЕ, до всего остального:
#   ssh -i ~/.ssh/<ключ> root@<ip> 'bash -s' < research_lab/vps_preflight.sh
#
# Пороги выведены из диагноза 64.226.73.119 (VPS_DIAGNOZ_2026_09_29.md),
# где перенос пришлось отменить: 1 ядро, 33 Mi свободной памяти,
# io full avg300 = 10 %. Каждый порог ниже отвечает за одну из этих бед.
#
# Код возврата: 0 — PASS, 1 — FAIL. Пригодно для скриптов.

vsego=0; upalo=0; predupr=0

ok ()   { printf "  [ PASS ] %-34s %s\n" "$1" "$2"; vsego=$((vsego+1)); }
bad ()  { printf "  [ FAIL ] %-34s %s\n" "$1" "$2"; vsego=$((vsego+1)); upalo=$((upalo+1)); }
warn () { printf "  [ warn ] %-34s %s\n" "$1" "$2"; predupr=$((predupr+1)); }

echo "PREFLIGHT  $(hostname)  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo

# ── процессор ────────────────────────────────────────────────────────
echo "ПРОЦЕССОР"
YADER=$(nproc)
if [ "$YADER" -ge 2 ]; then ok "ядер >= 2" "$YADER"
else bad "ядер >= 2" "$YADER — фабрика считает перестановочные тесты на полном ядре"; fi

LA1=$(awk '{print $1}' /proc/loadavg)
PORLA=$(awk -v y="$YADER" 'BEGIN{printf "%.2f", y*0.7}')
if awk -v a="$LA1" -v p="$PORLA" 'BEGIN{exit !(a<p)}'; then ok "load average 1m < ${PORLA}" "$LA1"
else bad "load average 1m < ${PORLA}" "$LA1 — машина уже занята"; fi

# ── память ───────────────────────────────────────────────────────────
echo
echo "ПАМЯТЬ"
MT=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
MA=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
ST=$(awk '/SwapTotal/{print int($2/1024)}' /proc/meminfo)
SF=$(awk '/SwapFree/{print int($2/1024)}' /proc/meminfo)
SU=$((ST-SF))

if [ "$MT" -ge 1900 ]; then ok "RAM всего >= 1900 Mi" "${MT} Mi"
else bad "RAM всего >= 1900 Mi" "${MT} Mi — три процесса с numpy это 250-400 Mi RSS"; fi
[ "$MT" -lt 3800 ] && [ "$MT" -ge 1900 ] && warn "RAM < 3800 Mi" "${MT} Mi — хватит, но без запаса на рост истории"

if [ "$MA" -ge 1200 ]; then ok "RAM доступно >= 1200 Mi" "${MA} Mi"
else bad "RAM доступно >= 1200 Mi" "${MA} Mi — именно здесь умер прошлый сервер (было 33 Mi)"; fi

if [ "$ST" -eq 0 ]; then warn "своп" "своп не настроен — при всплеске сработает OOM killer"
elif [ "$SU" -lt $((ST/10+1)) ]; then ok "своп занят < 10 %" "${SU} из ${ST} Mi"
else bad "своп занят < 10 %" "${SU} из ${ST} Mi — машина уже свопится"; fi

# ── диск ─────────────────────────────────────────────────────────────
echo
echo "ДИСК"
SVOB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
PROC=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "$SVOB" -ge 15 ]; then ok "свободно на / >= 15 G" "${SVOB} G"
else bad "свободно на / >= 15 G" "${SVOB} G — одно состояние занимает ~200 M и растёт"; fi
if [ "$PROC" -lt 80 ]; then ok "занято на / < 80 %" "${PROC} %"
else bad "занято на / < 80 %" "${PROC} %"; fi

# ── давление ─────────────────────────────────────────────────────────
echo
echo "ДАВЛЕНИЕ (PSI: сколько времени задачи ЖДУТ ресурс)"
psi () {                       # $1 файл, $2 строка some|full, $3 порог %
  local f="/proc/pressure/$1"
  [ -r "$f" ] || { warn "PSI $1 $2" "нет /proc/pressure — ядро старше 4.20"; return; }
  local v; v=$(awk -v k="$2" '$1==k{for(i=2;i<=NF;i++) if($i ~ /^avg300=/){sub("avg300=","",$i); print $i}}' "$f")
  [ -n "$v" ] || { warn "PSI $1 $2" "не прочитано"; return; }
  if awk -v a="$v" -v p="$3" 'BEGIN{exit !(a<p)}'; then ok "$1 $2 avg300 < $3 %" "$v %"
  else bad "$1 $2 avg300 < $3 %" "$v % — ресурс уже в дефиците"; fi
}
psi cpu    some 5
psi io     full 1
psi memory full 1

# ── питон ────────────────────────────────────────────────────────────
echo
echo "ПИТОН"
if command -v python3 >/dev/null 2>&1; then
  V=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
  if python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)'; then ok "python3 >= 3.9" "$V"
  else bad "python3 >= 3.9" "$V"; fi
  python3 -c 'import venv' 2>/dev/null && ok "модуль venv" "есть" \
    || warn "модуль venv" "нет — потребуется apt-get install -y python3-venv"
else bad "python3" "не найден"; fi

command -v systemctl >/dev/null 2>&1 && ok "systemd" "есть" \
  || warn "systemd" "нет — процессы не переживут перезагрузку сервера"

# ── итог ─────────────────────────────────────────────────────────────
echo
echo "───────────────────────────────────────────────"
printf "проверок %s, провалов %s, предупреждений %s\n" "$vsego" "$upalo" "$predupr"
if [ "$upalo" -eq 0 ]; then
  echo "ИТОГ: PASS — машина годится, можно переносить."
  exit 0
else
  echo "ИТОГ: FAIL — НЕ переносить. Каждый FAIL выше это отдельная причина."
  exit 1
fi
