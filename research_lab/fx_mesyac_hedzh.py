#!/usr/bin/env python3
"""fx_mesyac_hedzh.py — замороженный скрипт-судья FX_MESYAC_HEDZH (prereg/FX_MESYAC_HEDZH.json). Запускает только контроллер.
Месяц m: S = доходность US30 − доходность GER40 от закрытия последнего торг. дня m−1 до закрытия T−3 (3-й с конца торг. день
EURUSD в m). Позиция EURUSD = +знак(S) (акции США обогнали → иностранцы продают USD для хеджа → EURUSD вверх).
Вход закрытие T−3, выход закрытие последнего торг. дня m. Издержки 1.5 bps. Окна: PRIMARY 2008-02…2017-12, HOLDOUT 2018-01…2026-09.
PASS: ≥ 60 мес., среднее > 0, обе половины > 0, t ≥ 2.0; HOLDOUT SAME_SIGN → READY_FOR_BUILD; иначе KILL / PRIMARY_PASS_HOLDOUT_OPPOSITE."""
import collections, json, math, sys
from pathlib import Path
import numpy as np
L = Path(__file__).resolve().parent; D = L / "data"; OUT = D / "fabrika_xs/FX_MESYAC_HEDZH_rezultat.json"
if OUT.exists():
    sys.exit("результат уже есть")
def z(n): return {b[0]: b[4] for b in json.loads((D / f"mt5_d1/{n}.json").read_text())["bary"]}
eu, us, de = z("EURUSD"), z("US30"), z("GER40")
po = collections.defaultdict(list)
for d in sorted(eu):
    if "2008-01-01" <= d <= "2026-09-30": po[d[:7]].append(d)
mes = sorted(po); sob = []
for a, b in zip(mes, mes[1:]):
    dn = po[b]
    if len(dn) < 10: continue
    d0, d3, dk = po[a][-1], dn[-3], dn[-1]
    if not all(x in us and x in de for x in (d0, d3)): continue
    S = (us[d3] / us[d0] - 1) - (de[d3] / de[d0] - 1)
    r = eu[dk] / eu[d3] - 1
    sob.append(dict(m=b, S=S, r=float(np.sign(S) * r - 0.00015), vsegda_long=r))
rez = {}
for imya, (a, b) in {"PRIMARY": ("2008-02", "2017-12"), "HOLDOUT": ("2018-01", "2026-09")}.items():
    v = np.array([x["r"] for x in sob if a <= x["m"] <= b]); h = len(v) // 2
    t = float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v))))
    rez[imya] = dict(mesyacev=len(v), srednee_bps=round(v.mean() * 1e4, 2), t=round(t, 2),
                     polovinki_bps=[round(v[:h].mean() * 1e4, 2), round(v[h:].mean() * 1e4, 2)], dolya_plyus=round(float((v > 0).mean()), 2))
p, ho = rez["PRIMARY"], rez["HOLDOUT"]
pp = p["mesyacev"] >= 60 and p["srednee_bps"] > 0 and min(p["polovinki_bps"]) > 0 and p["t"] >= 2.0
ho["status"] = "SAME_SIGN" if ho["srednee_bps"] > 0 else "OPPOSITE"
rez["status"] = "READY_FOR_BUILD" if pp and ho["status"] == "SAME_SIGN" else ("PRIMARY_PASS_HOLDOUT_OPPOSITE" if pp else "KILL")
OUT.write_text(json.dumps(dict(rez, sobytiya=sob), ensure_ascii=False, indent=1))
print(json.dumps(rez, ensure_ascii=False))
