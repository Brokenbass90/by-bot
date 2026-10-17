#!/usr/bin/env python3
"""Измерения PREREG_ETF_OBEM_VOL_KONTEKST_2026_10_17 (M1–M3). Без доходностей по направлению."""
import datetime as dt, json
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; H, DEN = 3_600_000, 86_400_000
z = np.load(LAB / "data/h1/BTCUSDT.npz"); ts = z["ts"].astype(np.int64); c = z["ohlcv"][:, 3].astype(float)
idx = {int(t): i for i, t in enumerate(ts)}; lr = np.diff(np.log(c))      # lr[i] = доходность бара i+1


def vol(i, posle=True):
    a, b = (i, i + 24) if posle else (i - 24, i)
    if a < 1 or b > len(lr) or ts[b] - ts[a] != 24 * H: return None
    return float(np.std(lr[a - 1:b - 1] if posle else lr[a - 1:b - 1], ddof=1))


sob = [e["t_ms"] for e in json.loads((LAB / "data/etf_premiya/sobytiya_OBEM_v1.json").read_text())]
otn_po, otn_do, vyshe = [], [], []
for t in sob:
    i = idx.get(t)
    if i is None: continue
    kontr = []
    for k in range(-60, 61):
        tk = t + k * DEN
        if abs(k) < 3 or any(abs(tk - s) < 3 * DEN for s in sob): continue
        if dt.datetime.fromtimestamp(tk / 1000, dt.timezone.utc).weekday() >= 5: continue
        j = idx.get(tk)
        if j is None: continue
        vp, vd = vol(j), vol(j, False)
        if vp and vd: kontr.append((vp, vd))
    vp, vd = vol(i), vol(i, False)
    if not (vp and vd and len(kontr) >= 20): continue
    mp = float(np.median([a for a, _ in kontr])); md = float(np.median([b for _, b in kontr]))
    otn_po.append(vp / mp); otn_do.append(vd / md); vyshe.append(vp > mp)
M1, M3, M2 = float(np.median(otn_po)), float(np.median(otn_do)), float(np.mean(vyshe))
rez = dict(n=len(otn_po), M1_posle=round(M1, 3), M2_dolya_vyshe=round(M2, 3), M3_do=round(M3, 3),
           verdikt="PASS" if M1 >= 1.2 and M2 >= 0.6 and M1 > M3 else "FAIL")
(LAB / "data/etf_premiya/OBEM_VOL_izmereniya.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
print(json.dumps(rez, ensure_ascii=False))
