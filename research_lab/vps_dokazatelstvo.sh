#!/bin/bash
# vps_dokazatelstvo.sh — доказать, что перезапуск НЕ теряет состояние.
# Запускать НА VPS после vps_zdorovye.sh = PASS.
#
# Что именно доказывается:
#   1. после остановки писателей ровно ноль — значит гасится всё;
#   2. после подъёма писателей ровно по одному — значит дублей нет;
#   3. счётчики продолжились, а не обнулились;
#   4. момент старта тени не изменился — проспективность цела;
#   5. службы включены в автозапуск — переживут и перезагрузку сервера.
# Код возврата: 0 — PASS, 1 — FAIL.
set -uo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"
case "$KOREN" in */research-24x7/*) : ;; *) echo "СТОП: не каталог исследования"; exit 1 ;; esac

SLUZHBY=(research-yadro_ETS2M research-ten_SILA research-fabrika)
MARKERY=("yadro.py --epoha ETS2M" "ten_sila.py" "fabrika.py --demon")
upalo=0
ok ()  { printf "  [ PASS ] %s\n" "$1"; }
bad () { printf "  [ FAIL ] %s\n" "$1"; upalo=$((upalo+1)); }

echo "ДОКАЗАТЕЛЬСТВО ПЕРЕЗАПУСКА  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo
echo "== 1. состояние ДО =="
python3 research_lab/vps_sostoyanie.py > /tmp/do_perezapuska.json
python3 -c "
import json; d=json.load(open('/tmp/do_perezapuska.json'))
for k in ('ets2m_vhodov','ets2m_ishodov','sila_resheniy','sila_nachalo','fabrika_verdiktov'):
    print('  %-20s %s' % (k, d.get(k)))"

echo
echo "== 2. гашу всё =="
for s in "${SLUZHBY[@]}"; do systemctl stop "$s"; done
sleep 5
zhivyh=0
for m in "${MARKERY[@]}"; do
  k=$(pgrep -fc -- "$m" 2>/dev/null || echo 0); zhivyh=$((zhivyh+k))
  printf "  %-26s %s\n" "$m" "$k"
done
[ "$zhivyh" -eq 0 ] && ok "писателей ноль — гасится всё" \
                    || bad "осталось живых процессов: $zhivyh"

echo
echo "== 3. поднимаю заново =="
PROPUSTIT_SVERKU=da bash research_lab/vps_zapusk.sh >/dev/null
sleep 20
for i in 0 1 2; do
  k=$(pgrep -fc -- "${MARKERY[$i]}" 2>/dev/null || echo 0)
  [ "$k" -eq 1 ] && ok "${SLUZHBY[$i]}: писателей 1" \
                 || bad "${SLUZHBY[$i]}: писателей $k"
done

echo
echo "== 4. состояние ПОСЛЕ =="
python3 - <<'PY'
import json, subprocess, sys
from pathlib import Path
LAB = Path("research_lab")
do = json.load(open("/tmp/do_perezapuska.json"))
posle = json.loads(subprocess.run([sys.executable, str(LAB / "vps_sostoyanie.py")],
                                  capture_output=True, text=True, check=True).stdout)
bad = 0
for k in ("sila_nachalo", "ets2m_epoha_sha"):
    if do.get(k) == posle.get(k):
        print("  [ PASS ] %-24s не изменилось" % k)
    else:
        bad += 1
        print("  [ FAIL ] %-24s %s → %s" % (k, do.get(k), posle.get(k)))
for k in ("ets2m_vhodov", "ets2m_ishodov", "sila_resheniy", "fabrika_verdiktov",
          "fabrika_punktov", "reestr_zapisey"):
    x, y = do.get(k), posle.get(k)
    if x is not None and y is not None and y >= x:
        print("  [ PASS ] %-24s %s → %s" % (k, x, y))
    else:
        bad += 1
        print("  [ FAIL ] %-24s %s → %s  ОБНУЛИЛОСЬ ИЛИ УПАЛО" % (k, x, y))
sys.exit(1 if bad else 0)
PY
[ $? -eq 0 ] || upalo=$((upalo+1))

echo
echo "== 5. переживут ли перезагрузку сервера =="
for s in "${SLUZHBY[@]}"; do
  e=$(systemctl is-enabled "$s" 2>/dev/null || true)
  [ "$e" = "enabled" ] && ok "$s: автозапуск enabled" || bad "$s: автозапуск $e"
done

echo
echo "───────────────────────────────────────────────"
if [ "$upalo" -eq 0 ]; then
  echo "ИТОГ: PASS — перезапуск состояние не теряет, дублей нет."
  exit 0
fi
echo "провалов: $upalo"
echo "ИТОГ: FAIL — Mac НЕ гасить."
exit 1
