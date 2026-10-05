#!/usr/bin/env python3
"""Диагностика признаков PUSTOY_HOD БЕЗ доходностей вперёд: ранговые корреляции сигналов на одних датах."""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sudya_xs as X
M = X.zagruzit(X.LAB / "data" / "binance_kity")
def rang(v): return np.argsort(np.argsort(v))
setka = [dt.date(2023, 1, 5) + dt.timedelta(days=7 * k) for k in range(195) if dt.date(2023, 1, 5) + dt.timedelta(days=7 * k) <= dt.date(2026, 9, 23)]
kor = {"ost~taker_d1": [], "ost~ret7": [], "ost~taker7": []}; nmon = []
for d in setka:
    vch = (d - dt.timedelta(days=1)).isoformat()
    oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
    rows = []
    for _, s in oi:
        x = M[s]; i = int(np.searchsorted(x["ts"], X.ms(d)))
        if i >= len(x["ts"]) or x["ts"][i] != X.ms(d) or i < 60:
            continue
        p = X.znachenie({"tip": "ost_ret7_taker7"}, x, i, vch); t1 = x["taker"].get(vch)
        if p is not None and t1 is not None:
            rows.append((p[0], p[1], t1))
    if len(rows) < 30:
        continue
    a = np.array(rows); A = np.vstack([np.ones(len(a)), a[:, 1]]).T; ost = a[:, 0] - A @ np.linalg.lstsq(A, a[:, 0], rcond=None)[0]
    nmon.append(len(a))
    for k, v in (("ost~taker_d1", a[:, 2]), ("ost~ret7", a[:, 0]), ("ost~taker7", a[:, 1])):
        kor[k].append(np.corrcoef(rang(ost), rang(v))[0, 1])
print("дат:", len(nmon), "монет в среднем:", round(float(np.mean(nmon)), 1))
for k, v in kor.items():
    print(f"  ранговая корр. {k}: среднее {np.mean(v):.2f}, медиана {np.median(v):.2f}")
