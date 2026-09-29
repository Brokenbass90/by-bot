#!/bin/bash
# vps_zapusk.sh — поднять три долгоживущих исследовательских процесса НА VPS.
#
# Ни ордеров, ни ключей, ни брокера: всё три ходят только в публичные
# endpoint'ы Bybit и Polymarket методом GET. Деньги здесь невозможны
# по построению.
#
# Запускать ТОЛЬКО из отдельного каталога исследования, не из продакшна Codex.
set -euo pipefail

KOREN="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KOREN"

case "$KOREN" in
  */research-24x7/*) : ;;
  *) echo "СТОП: это не каталог исследования ($KOREN)."
     echo "Ожидается путь вида /root/research-24x7/by-bot — чтобы никогда"
     echo "не пересечься с продакшном Codex в /root/by-bot."; exit 1 ;;
esac

PY=""
for K in "$KOREN/.venv-research/bin/python3" "$KOREN/.venv/bin/python3" "$(command -v python3)"; do
  [ -x "$K" ] || continue
  "$K" -c 'import numpy' >/dev/null 2>&1 && { PY="$K"; break; }
done
[ -n "$PY" ] || { echo "НЕ НАШЁЛ python3 с numpy. Ничего не поднято."; exit 1; }
echo "питон: $PY"

LOGI="$KOREN/research_lab/data"
mkdir -p "$LOGI"

podnyat () {
  local imya="$1"; shift
  local marker="$1"; shift
  if pgrep -f "$marker" >/dev/null 2>&1; then
    echo "  $imya: уже работает (pgrep '$marker')"; return
  fi
  nohup "$PY" "$@" >> "$LOGI/vps_${imya}.log" 2>&1 &
  echo "  $imya: поднят, процесс $!"
}

echo "ПОДНИМАЮ ИССЛЕДОВАНИЕ  $(date -u '+%Y-%m-%d %H:%M UTC')"
podnyat "yadro_ETS2M" "yadro.py --epoha ETS2M" \
        research_lab/yadro.py --epoha ETS2M --minut 100000000 --pauza 3600
sleep 2
podnyat "ten_SILA"    "ten_sila.py" \
        research_lab/ten_sila.py --minut 100000000 --pauza 21600
sleep 2
podnyat "fabrika"     "fabrika.py --demon" \
        research_lab/fabrika/fabrika.py --demon

echo
echo "проверить:  bash research_lab/vps_proverka.sh"
