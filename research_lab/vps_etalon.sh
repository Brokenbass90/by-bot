#!/bin/bash
# vps_etalon.sh — снять эталон состояния НА MAC. Только чтение.
#
# Запускать НЕПОСРЕДСТВЕННО перед перевозкой: Mac продолжает писать,
# и эталон, снятый за несколько часов, не сойдётся и вызовет ложную тревогу.
# Файл кладётся в белый список и уезжает вместе с состоянием.
set -euo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"
CEL="research_lab/data/ETALON_PERENOSA.json"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
python3 research_lab/vps_sostoyanie.py > "$TMP"
python3 - "$TMP" "$CEL" <<'PY'
import json, sys, datetime
s = json.load(open(sys.argv[1], encoding="utf-8"))
s["_snyat"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
json.dump(s, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2, sort_keys=True)
PY
echo "эталон записан: $CEL"
echo
cat "$CEL"
echo
echo "Теперь сразу:  SERVER=root@<ip> bash research_lab/perenos_na_vps.sh --vezti"
