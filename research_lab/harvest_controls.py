#!/usr/bin/env python3
"""harvest_controls.py — свести контроли по всем ногам в один список.

Отбор объявлен до чтения: эдж положителен на ОБОИХ окнах,
сделок не меньше 200 и 100, значимость эджа на первом окне >= 2.0.
Отдельно помечаем тех, у кого знак совпал, но сила только на одном окне.
"""
import re, sys
from pathlib import Path

txt = Path("research_lab/controls_all.log").read_text(encoding="utf-8")
blocks = re.split(r"\n(?=[A-Z0-9]+: (?:short|long))", txt)
rows = []
for b in blocks:
    m = re.match(r"([A-Z0-9]+): (short|long), стоп ×([\d.]+), держ (\d+) ч, режим «([^»]+)»", b.strip())
    if not m:
        continue
    leg, side, mult, hold, reg = m.groups()
    ws = re.findall(r"(20\d\d-\d\d\.\.20\d\d-\d\d)\s+(\d+)\s+([+-][\d.]+)R\s+([+-][\d.]+)R\s+([\d.]+)R\s+([+-][\d.]+)R\s+([+-][\d.]+)", b)
    if len(ws) != 2:
        continue
    (w1, n1, s1, c1, d1, e1, z1), (w2, n2, s2, c2, d2, e2, z2) = ws
    rows.append(dict(leg=leg, side=side, mult=mult, reg=reg,
                     n1=int(n1), e1=float(e1), z1=float(z1),
                     n2=int(n2), e2=float(e2), z2=float(z2)))

print(f"прочитано прогонов с данными: {len(rows)} из 98\n")
good = [r for r in rows if r["e1"] > 0 and r["e2"] > 0 and r["n1"] >= 200 and r["n2"] >= 100 and r["z1"] >= 2.0]
half = [r for r in rows if r["e1"] > 0 and r["n1"] >= 200 and r["z1"] >= 2.0 and r not in good]
bad  = [r for r in rows if r["e1"] < 0 and r["z1"] <= -2.0 and r["n1"] >= 200]

def show(title, lst):
    print(f"╔══ {title}: {len(lst)}")
    if not lst:
        print("   пусто\n"); return
    print(f"   {'нога':<8}{'сторона':<7}{'стоп':<6}{'режим':<8}"
          f"{'окно1 эдж':>12}{'σ':>7}{'n':>6}{'окно2 эдж':>12}{'σ':>7}{'n':>6}")
    for r in sorted(lst, key=lambda x: -x["z1"])[:15]:
        print(f"   {r['leg']:<8}{r['side']:<7}{r['mult']:<6}{r['reg']:<8}"
              f"{r['e1']:>+11.4f}R{r['z1']:>+7.2f}{r['n1']:>6}"
              f"{r['e2']:>+11.4f}R{r['z2']:>+7.2f}{r['n2']:>6}")
    print()

show("ЭДЖ НАД СЛУЧАЙНОСТЬЮ на обоих окнах", good)
show("эдж только на первом окне", half)
show("ЗНАЧИМО ХУЖЕ случайного входа", bad)
