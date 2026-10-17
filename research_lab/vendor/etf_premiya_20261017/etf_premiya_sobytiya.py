#!/usr/bin/env python3
"""ETF_PREMIYA события (заморожено 17.10.2026 до доходностей).
premiya_t как в etf_premiya_izmereniya.py; z_t = premiya_t / sd(premiya за 60 ПРЕДЫДУЩИХ сессий), ≥ 40 сессий истории.
Событие: |z| ≥ 1.5; момент = закрытие NYSE + 1 ч; знак = sign(z) (премия = спрос → создание паёв → покупка спота).
"""
import json, sys, hashlib, datetime as dt
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_premiya_izmereniya as M
LAB = M.LAB

def sobytiya(tiker, simvol, porog_z=1.5, okno=60, min_ist=40):
    e = M.etf_ryad({tiker}); cn = M.coin_na_zakrytii(simvol)
    rd, rat = [], {}
    for d in sorted(e):
        if tiker in e[d]:
            p = cn(d)
            if p: rat[d] = e[d][tiker] / p; rd.append(d)
    prem = {}
    for i, d in enumerate(rd):
        if i >= 20: prem[d] = rat[d] / float(np.median([rat[x] for x in rd[i - 20:i]])) - 1
    pd = sorted(prem); ev = []
    for i, d in enumerate(pd):
        ist = [prem[x] for x in pd[max(0, i - okno):i]]
        if len(ist) < min_ist: continue
        sd = float(np.std(ist, ddof=1)); z = prem[d] / sd if sd > 0 else 0.0
        if abs(z) >= porog_z:
            close = dt.datetime.combine(dt.date.fromisoformat(d), dt.time(16, 0), M.NY).astimezone(dt.timezone.utc)
            ev.append(dict(t_ms=int((close + dt.timedelta(hours=1)).timestamp() * 1000), simvol=simvol,
                           znak=1 if z > 0 else -1, den=d, z=round(z, 2), premiya_bps=round(1e4 * prem[d], 1)))
    return ev

if __name__ == "__main__":
    out = LAB / "data/etf_premiya"; out.mkdir(exist_ok=True); man = dict(gotovo=True, pravila=dict(porog_z=1.5, okno=60, min_ist=40, lag_ch=1))
    for t, s in (("IBIT", "BTCUSDT"), ("ETHA", "ETHUSDT")):
        ev = sobytiya(t, s); f = out / f"sobytiya_{t}_v1.json"
        f.write_text(json.dumps([{k: x[k] for k in ("t_ms", "simvol", "znak")} for x in ev]))
        (out / f"sobytiya_{t}_v1_detali.json").write_text(json.dumps(ev, ensure_ascii=False))
        g = {}
        for x in ev: g[x["den"][:4]] = g.get(x["den"][:4], 0) + 1
        man[t] = dict(sobytiy=len(ev), plyus=sum(x["znak"] == 1 for x in ev), minus=sum(x["znak"] == -1 for x in ev), po_godam=g,
                      sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    man["kod_sha256"] = {n: hashlib.sha256((LAB / "fabrika" / n).read_bytes()).hexdigest()
                         for n in ("etf_premiya_sobytiya.py", "etf_premiya_izmereniya.py")}
    (out / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1)); print(json.dumps(man, ensure_ascii=False))
