#!/bin/bash
# vps_proverka.sh — только чтение. Отвечает на один вопрос:
# состояние доехало целым и пишет ли его ровно один процесс.
set -euo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"
PY="$(command -v python3)"
for K in "$KOREN/.venv-research/bin/python3" "$KOREN/.venv/bin/python3"; do
  [ -x "$K" ] && "$K" -c 'import numpy' >/dev/null 2>&1 && PY="$K" && break
done

echo "== СОСТОЯНИЕ =="
"$PY" - <<'PYEOF'
import json, os, time
def n(p):
    return sum(1 for _ in open(p, encoding="utf-8", errors="ignore")) if os.path.exists(p) else None
print("  ETS2M входов          :", n("research_lab/data/yadro/ETS2M/vhody.jsonl"))
print("  ETS2M исходов         :", n("research_lab/data/yadro/ETS2M/ishody.jsonl"))
e = "research_lab/data/yadro/ETS2M/epoha.json"
if os.path.exists(e):
    d = json.load(open(e))
    print("  ETS2M эпоха           :", {k: v for k, v in list(d.items())[:4]})
s = "research_lab/data/ten_SILA_sostoyanie.json"
if os.path.exists(s):
    print("  SILA момент старта    :", json.load(open(s)).get("nachalo"))
print("  SILA решений          :", n("research_lab/data/ten_SILA.jsonl"))
print("  фабрика: вердиктов    :", n("research_lab/fabrika/verdikty.jsonl"))
o = "research_lab/fabrika/ochered.json"
if os.path.exists(o):
    print("  фабрика: пунктов      :", len(json.load(open(o))["ochered"]))
b = "research_lab/data/ten_SILA.bienie"
if os.path.exists(b):
    print("  SILA биение, ч назад  : %.1f" % ((time.time() - float(open(b).read())) / 3600))
PYEOF

echo
echo "== ПИСАТЕЛИ (должно быть ровно по одному) =="
for m in "yadro.py --epoha ETS2M" "ten_sila.py" "fabrika.py --demon"; do
  k=$(pgrep -fc "$m" 2>/dev/null || echo 0)
  printf "  %-26s %s\n" "$m" "$k"
  [ "$k" -gt 1 ] && echo "     ДУБЛЬ! Остановите лишний."
done
echo
echo "== СВЕЖЕСТЬ ЛОГОВ =="
for f in research_lab/data/vps_yadro_ETS2M.log research_lab/data/vps_ten_SILA.log research_lab/data/vps_fabrika.log; do
  [ -f "$f" ] && printf "  %-44s %s\n" "$f" "$(date -u -r "$f" '+%Y-%m-%d %H:%M' 2>/dev/null || stat -c %y "$f" | cut -c1-16)"
done
