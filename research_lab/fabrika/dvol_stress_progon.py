#!/usr/bin/env python3
"""Прогон PREREG_DVOL_I_STRESS_RAZMER_2026_10_17 (f0c309d). Сделки и метрики — из vol_razmer_progon (без изменений)."""
import bisect, contextlib, io, json, runpy
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; H, DEN = 3_600_000, 86_400_000
with contextlib.redirect_stdout(io.StringIO()):
    B = runpy.run_path(str(LAB / "fabrika/vol_razmer_progon.py"))
sdelki, metriki, IZD = B["sdelki"], B["metriki"], B["IZD"]
dv = {int(z[0]): float(z[4]) for z in json.loads((LAB / "data/deribit/dvol_BTC.json").read_text())["ryad"]}
fu = json.loads((LAB / "data/binance/funding/BTCUSDT.json").read_text()); fu_t = [int(x[0]) for x in fu]


def razmer_dvol(t):
    tek = dv.get(t - H)                                         # свеча [t−1ч, t) закрыта к входу
    ist = [dv[k] for k in range(t - 720 * H, t, H) if k in dv]
    if tek is None or len(ist) < 600: return None
    return float(np.clip(np.median(ist) / tek, 0.25, 2.0))


def razmer_stress(t):
    j = bisect.bisect_right(fu_t, t) - 1
    if j < 0: return None
    ist = [fu[k][1] for k in range(bisect.bisect_left(fu_t, t - 90 * DEN), j + 1)]
    if len(ist) < 200: return 1.0                              # дополнение 1: короткая история → не вмешиваться
    lo, hi = np.percentile(ist, [5, 95]); return 0.5 if not (lo <= fu[j][1] <= hi) else 1.0


rez = {}
for imya, f in (("DVOL_RAZMER_V1", razmer_dvol), ("STRESS_RAZMER_V1", razmer_stress)):
    razm = [f(s["t"]) for s in sdelki]
    if any(r is None for r in razm): rez[imya] = dict(verdikt="BLOCKED", propuskov=sum(r is None for r in razm)); continue
    sr = float(np.mean(razm)); out = dict(n_sdelok=len(sdelki), sredniy_razmer=round(sr, 4), potoki={}); ok = True
    for nm, znak in (("LONG", 1), ("SHORT", -1)):
        mc = metriki([sr * (znak * s["r"] - IZD) for s in sdelki], [sr] * len(sdelki))
        mh = metriki([r * (znak * s["r"] - IZD) for r, s in zip(razm, sdelki)], razm)
        usl = dict(prosadka=mh["maks_prosadka"] <= 0.85 * mc["maks_prosadka"], cvar5=mh["cvar5"] >= 0.85 * mc["cvar5"],
                   pnl=mh["chistyy_pnl"] >= mc["chistyy_pnl"] - 0.10 * abs(mc["chistyy_pnl"]))
        ok &= all(usl.values()); out["potoki"][nm] = dict(POSTOYANNYY=mc, POLITIKA=mh, usloviya=usl)
    out["verdikt"] = "PASS" if ok else "FAIL"; rez[imya] = out
(LAB / "data/factory_v3/DVOL_STRESS_rezultat.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
for k, v in rez.items():
    print(k, v["verdikt"], v.get("sredniy_razmer"))
    for nm, p in v.get("potoki", {}).items():
        a, b = p["POSTOYANNYY"], p["POLITIKA"]
        print(f"  {nm}: DD {a['maks_prosadka']}→{b['maks_prosadka']} ({100*(b['maks_prosadka']/a['maks_prosadka']-1):+.0f}%), CVaR5 {a['cvar5']}→{b['cvar5']}, PnL {a['chistyy_pnl']}→{b['chistyy_pnl']}, худшая {a['hudshaya']}→{b['hudshaya']}, пик {b['kapital_pik']}")
