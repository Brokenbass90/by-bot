#!/usr/bin/env python3
"""Диагностика признаков FX_MESYAC_HEDZH БЕЗ доходностей EURUSD вперёд. Правило выбора (записано до расчёта):
M2 = US30 − GER40 с начала месяца (то, что задаёт теория хеджа: относительная доходность акций) — берётся, если покрытие
≥ 90% месяцев 2008-02…2026-09; иначе M1 = только US30. Корреляция M1/M2 — справочно."""
import collections, json
from pathlib import Path
import numpy as np
D = Path(__file__).resolve().parents[1] / "data"
def z(n): return {b[0]: b[4] for b in json.loads((D / f"mt5_d1/{n}.json").read_text())["bary"]}
eu, us, de = z("EURUSD"), z("US30"), z("GER40")
po = collections.defaultdict(list)
for d in sorted(eu):
    if "2008-01-01" <= d <= "2026-09-30": po[d[:7]].append(d)
mes = sorted(po); m1, m2, vsego = [], [], 0
for a, b in zip(mes, mes[1:]):
    dn = po[b]; vsego += 1
    if len(dn) < 10: continue
    d0, d3 = po[a][-1], dn[-3]
    if d0 in us and d3 in us:
        r_us = us[d3] / us[d0] - 1; m1.append(r_us)
        if d0 in de and d3 in de: m2.append((r_us, r_us - (de[d3] / de[d0] - 1)))
pokr = len(m2) / vsego
v = np.array(m2)
rez = dict(mesyacev=vsego, pokrytie_M1=round(len(m1) / vsego, 3), pokrytie_M2=round(pokr, 3),
           korr_M1_M2=round(float(np.corrcoef(v[:, 0], v[:, 1])[0, 1]), 3),
           izmerenie_vybrano="M2" if pokr >= 0.9 else "M1", dohodnosti_vpered="не считались")
(D / "fabrika_xs/diagnostika/FX_MESYAC_HEDZH.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(rez)
