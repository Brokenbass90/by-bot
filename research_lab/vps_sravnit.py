#!/usr/bin/env python3
"""vps_sravnit.py — сравнить состояние с эталоном переноса.

  --rezhim do      до запуска служб: расти нечему, требуется точное равенство
  --rezhim posle   после запуска: счётчики обязаны расти, а не падать,
                   а момент старта тени и эпоха ETS2M — не меняться вообще

Код возврата: 0 — PASS, 1 — FAIL.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent

# Поля, расхождение в которых означает потерю проспективности,
# а не просто несовпадение чисел.
NEIZMENNY = ("sila_nachalo", "ets2m_epoha_sha")
RASTUT = ("ets2m_vhodov", "ets2m_ishodov", "ets2m_ispolneniy",
          "sila_resheniy", "fabrika_verdiktov", "reestr_istorii_strok")

p = argparse.ArgumentParser()
p.add_argument("--rezhim", choices=("do", "posle"), required=True)
p.add_argument("--etalon", default=str(LAB / "data/ETALON_PERENOSA.json"))
a = p.parse_args()

et_f = Path(a.etalon)
if not et_f.exists():
    print("НЕТ ЭТАЛОНА: %s" % et_f)
    print("Значит перевозка шла без vps_etalon.sh. Сверять не с чем.")
    print("ИТОГ: FAIL")
    sys.exit(1)

et = json.loads(et_f.read_text(encoding="utf-8"))
snyat = et.pop("_snyat", "?")
fk = json.loads(subprocess.run([sys.executable, str(LAB / "vps_sostoyanie.py")],
                               capture_output=True, text=True, check=True).stdout)

print("эталон снят на Mac: %s" % snyat)
print()
upalo = 0

for k in NEIZMENNY:
    x, y = et.get(k), fk.get(k)
    if x == y:
        print("  [ PASS ] %-28s %s" % (k, y))
    else:
        upalo += 1
        print("  [ FAIL ] %-28s было %s, стало %s   КРИТИЧНО" % (k, x, y))

if a.rezhim == "do":
    for k in sorted(set(et) | set(fk)):
        if k in NEIZMENNY:
            continue
        x, y = et.get(k, "<нет в эталоне>"), fk.get(k, "<нет на VPS>")
        if x == y:
            print("  [ PASS ] %-28s %s" % (k, x))
        else:
            upalo += 1
            metka = "   КРИТИЧНО" if k in RASTUT else ""
            print("  [ FAIL ] %-28s Mac=%s  VPS=%s%s" % (k, x, y, metka))
else:
    for k in RASTUT:
        x, y = et.get(k), fk.get(k)
        if x is None or y is None:
            upalo += 1
            print("  [ FAIL ] %-28s нет данных (Mac=%s VPS=%s)" % (k, x, y))
        elif y >= x:
            print("  [ PASS ] %-28s %s → %s  (+%s)" % (k, x, y, y - x))
        else:
            upalo += 1
            print("  [ FAIL ] %-28s %s → %s  СЧЁТЧИК УПАЛ" % (k, x, y))

print()
if upalo == 0:
    print("расхождений нет")
    print("ИТОГ: PASS")
    sys.exit(0)
print("расхождений: %d" % upalo)
if a.rezhim == "do":
    print("ИТОГ: FAIL — НЕ запускать. Запуск на расходящемся состоянии")
    print("        начнёт вторую историю там, где должна продолжиться первая.")
else:
    print("ИТОГ: FAIL — контур не здоров.")
sys.exit(1)
