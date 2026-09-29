#!/bin/bash
# vps_zapusk.sh — поднять три службы исследования. Запускать НА VPS.
# Запуск разрешён только после PASS от vps_sverka.sh.
set -euo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"

case "$KOREN" in
  */research-24x7/*) : ;;
  *) echo "СТОП: это не каталог исследования ($KOREN)."; exit 1 ;;
esac

if [ "${PROPUSTIT_SVERKU:-}" != "da" ]; then
  echo "== сверка состояния перед запуском =="
  if ! bash research_lab/vps_sverka.sh > /tmp/sverka_pered_zapuskom.txt 2>&1; then
    tail -20 /tmp/sverka_pered_zapuskom.txt
    echo
    echo "СТОП: сверка не прошла. Запуск на расходящемся состоянии начнёт"
    echo "вторую историю там, где должна продолжиться первая."
    echo "Полный вывод: /tmp/sverka_pered_zapuskom.txt"
    exit 1
  fi
  echo "  сверка: PASS"
  echo
fi

for s in research-yadro_ETS2M research-ten_SILA research-fabrika; do
  systemctl start "$s"
  printf "  %-26s %s\n" "$s" "$(systemctl is-active "$s")"
done

echo
echo "через минуту:  bash research_lab/vps_zdorovye.sh"
