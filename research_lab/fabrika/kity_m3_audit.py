#!/usr/bin/env python3
"""kity_m3_audit.py — аудит причинности KITY M3 (описательно, вердикт не меняется): если в данных есть заглядывание вперёд
или ошибка времени, «устаревший» сигнал и перемешанный сигнал покажут странное. Ожидание при честных данных:
  исходный > сигнал с задержкой на неделю (d−8) > перемешанный ≈ −издержки."""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sudya_xs as X
M = X.zagruzit(X.LAB / "data" / "binance_kity"); rng = np.random.default_rng(11)
def prog(sdvig_dney=1, peremeshat=False):
    out = []; d = dt.date(2023, 1, 5)
    while d <= dt.date(2026, 9, 23):
        vch = (d - dt.timedelta(days=1)).isoformat(); vt = (d - dt.timedelta(days=sdvig_dney)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], X.ms(d)))
            if i >= len(x["ts"]) or x["ts"][i] != X.ms(d) or i < 60:
                continue
            z = x["taker"].get(vt)
            if z is not None:
                rows.append([z, s, i])
        if len(rows) >= 30:
            if peremeshat:
                zz = [r[0] for r in rows]; rng.shuffle(zz)
                for r, z in zip(rows, zz): r[0] = z
            rows.sort(); k = len(rows) // 10
            legs = [X.sdelka(M[s], i, 7, -1, .0012, dt.date(2026, 9, 30)) for _, s, i in rows[:k]] + \
                   [X.sdelka(M[s], i, 7, +1, .0012, dt.date(2026, 9, 30)) for _, s, i in rows[-k:]]
            legs = [l for l in legs if l is not None]
            if legs: out.append(np.mean(legs))
        d += dt.timedelta(days=7)
    v = np.array(out); return dict(nedel=len(v), bps=round(v.mean() * 1e4, 1), t=round(X.P.t_nw(v, 1), 2))
rez = {"исходный (taker d−1)": prog(1), "задержка: taker d−2": prog(2), "задержка: taker d−8": prog(8),
       "перемешанный (5 прогонов, среднее bps)": round(np.mean([prog(1, True)["bps"] for _ in range(5)]), 1)}
print(json.dumps(rez, ensure_ascii=False, indent=1))
(X.LAB / "data" / "binance_kity" / "KITY_M3_AUDIT_PRICHINNOSTI.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
