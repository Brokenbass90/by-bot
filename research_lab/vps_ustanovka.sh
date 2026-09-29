#!/bin/bash
# vps_ustanovka.sh — поставить исследование как службы. Запускать НА VPS.
#
# Почему systemd, а не nohup. Весь смысл переноса в том, чтобы процессы
# жили без присмотра. nohup не переживает перезагрузку сервера: одна
# перезагрузка — и мы возвращаемся ровно к той проблеме, из-за которой
# уезжали с Mac. systemd поднимает их сам и после падения, и после ребута.
#
# Службы НЕ запускаются здесь. Сначала сверка состояния (vps_sverka.sh).
set -euo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"

case "$KOREN" in
  */research-24x7/*) : ;;
  *) echo "СТОП: это не каталог исследования ($KOREN)."
     echo "Ожидается путь вида /root/research-24x7/by-bot — чтобы никогда"
     echo "не пересечься с продакшном Codex."; exit 1 ;;
esac

echo "== 1. окружение =="
if [ ! -x .venv-research/bin/python3 ]; then
  python3 -m venv .venv-research || {
    echo "venv не создался. Нужно: apt-get install -y python3-venv"; exit 1; }
fi
.venv-research/bin/pip install --quiet --upgrade pip
.venv-research/bin/pip install --quiet numpy
PY="$KOREN/.venv-research/bin/python3"
"$PY" -c 'import numpy; print("  numpy", numpy.__version__)'

echo
echo "== 2. чистка чужих замков =="
# Замки и биения с Mac не должны были приехать (они в исключениях rsync),
# но если приехали любым другим путём — снимаем. Чужой pid может совпасть
# с живым процессом на этой машине, и служба не поднимется без объяснений.
for f in research_lab/data/*.pid research_lab/data/*.bienie research_lab/fabrika/.zamok; do
  [ -e "$f" ] && { rm -f "$f"; echo "  снят: $f"; }
done
echo "  готово"

echo
echo "== 3. службы =="
mkdir -p research_lab/data

edinica () {                     # $1 имя, $2 описание, $3 nice, $4… команда
  local imya="$1" opis="$2" nice="$3"; shift 3
  local log="$KOREN/research_lab/data/vps_${imya}.log"
  cat > "/etc/systemd/system/research-${imya}.service" <<UNIT
[Unit]
Description=${opis}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${KOREN}
ExecStart=${PY} $*
Restart=always
RestartSec=30
StartLimitIntervalSec=600
StartLimitBurst=6
Nice=${nice}
StandardOutput=append:${log}
StandardError=append:${log}
# Ни ордеров, ни брокера: процессы ходят только в публичные GET.
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNIT
  echo "  research-${imya}.service  →  $log"
}

edinica "yadro_ETS2M" "ETS2M: когорта, 24/7" 5 \
        research_lab/yadro.py --epoha ETS2M --minut 100000000 --pauza 3600
edinica "ten_SILA" "Тень SILA: проспективные решения" 5 \
        research_lab/ten_sila.py --minut 100000000 --pauza 21600
# Фабрика считает бэктесты и перестановочные тесты. Ей самый низкий
# приоритет и idle-класс ввода-вывода, чтобы она никогда не мешала
# двум процессам, которые копят проспективные данные.
edinica "fabrika" "Фабрика: очередь исследований" 19 \
        research_lab/fabrika/fabrika.py --demon
sed -i '/^Nice=19$/a IOSchedulingClass=idle\nCPUWeight=20' \
       /etc/systemd/system/research-fabrika.service

systemctl daemon-reload
systemctl enable research-yadro_ETS2M research-ten_SILA research-fabrika >/dev/null 2>&1
echo "  включены в автозапуск (после перезагрузки поднимутся сами)"

echo
echo "УСТАНОВЛЕНО. Службы НЕ запущены — это делается после сверки:"
echo "  bash research_lab/vps_sverka.sh    # обязано быть PASS"
echo "  bash research_lab/vps_zapusk.sh"
