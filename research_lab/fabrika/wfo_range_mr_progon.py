#!/usr/bin/env python3
"""Прогон PREREG_WFO_RANGE_MR_2026_10_17 через wfo_v1."""
import datetime as dt, glob, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika"))
import wfo_v1 as W
kl = {}
for f in glob.glob(str(LAB / "data/factory_v3/wfo_range_mr/*.npy")):
    sym = Path(f).stem
    for tv, ty, s, Z, k, Hh, R in np.load(f):
        for st in ("LONG", "SHORT", "OBE"):
            if st == "LONG" and s < 0 or st == "SHORT" and s > 0: continue
            kl.setdefault(f"z{Z}_k{k}_h{int(Hh)}_{st}", []).append((sym, int(tv), int(ty), float(R)))
kl = {k: W.bez_perekrytiy(v) for k, v in kl.items()}
rez = W.progon(kl, dt.datetime(2023, 7, 1, tzinfo=W.UTC), dt.datetime(2026, 10, 1, tzinfo=W.UTC))
# отчётные (не вердикт): частота и просадка
vyb = {m: c for m, c, _, _ in rez["vybory"]}; nev = []
for m, c in vyb.items():
    if not c: continue
    a = dt.datetime.strptime(m, "%Y-%m").replace(tzinfo=W.UTC); b = W.mesyacy(a, a + dt.timedelta(days=1))[0][1]
    nev += [(x[1], x[3]) for x in kl[c] if W.ms(a) <= x[1] < W.ms(b)]
nev.sort(); kum = np.cumsum([r for _, r in nev]) if nev else np.array([0.0])
rez["prosadka_R"] = round(float(np.max(np.maximum.accumulate(np.r_[0, kum])[1:] - kum)), 1) if nev else None
rez["sdelok_v_sutki"] = round(len(nev) / max(1, (nev[-1][0] - nev[0][0]) / 86_400_000), 2) if nev else 0
rez["kletok"] = len(kl); rez["sdelok_v_kletkah"] = {k: len(v) for k, v in sorted(kl.items())}
(LAB / "data/factory_v3/WFO_RANGE_MR_rezultat.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
v = rez.pop("vybory"); rez.pop("sdelok_v_kletkah"); print(json.dumps(rez, ensure_ascii=False)); print(v)
