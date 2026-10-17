#!/usr/bin/env python3
"""Прогон PREREG_WFO_ASM1_2026_10_17: сделки из data/factory_v3/wfo_asm1 → wfo_v1.progon."""
import datetime as dt, glob, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika"))
import wfo_v1 as W
kl = {}
for f in glob.glob(str(LAB / "data/factory_v3/wfo_asm1/*.npy")):
    sym = Path(f).stem
    for tv, ty, s, k, Hh, R in np.load(f):
        for st in ("LONG", "SHORT", "OBE"):
            if st == "LONG" and s < 0 or st == "SHORT" and s > 0: continue
            kl.setdefault(f"k{int(k)}_h{int(Hh)}_{st}", []).append((sym, int(tv), int(ty), float(R)))
kl = {k: W.bez_perekrytiy(v) for k, v in kl.items()}
rez = W.progon(kl, dt.datetime(2023, 7, 1, tzinfo=W.UTC), dt.datetime(2026, 10, 1, tzinfo=W.UTC))
rez["kletok"] = len(kl); rez["sdelok_v_kletkah"] = {k: len(v) for k, v in sorted(kl.items())}
(LAB / "data/factory_v3/WFO_ASM1_rezultat.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
v = rez.pop("vybory"); rez.pop("sdelok_v_kletkah")
print(json.dumps(rez, ensure_ascii=False)); print(v)
