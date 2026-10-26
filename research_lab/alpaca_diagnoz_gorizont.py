"""Замеры PREREG_ALPACA_DIAGNOZ_GORIZONT_2026_10_26 на U2."""
import json, math, sys
from pathlib import Path
import numpy as np, pandas as pd
D = Path("data/alpaca_pit_daily_deep_20260925/bars")
C, V = {}, {}
for f in D.glob("*.json"):
    try: r = json.load(open(f))["records"]
    except Exception: continue
    if len(r) < 300: continue
    s = f.stem; t = pd.to_datetime([x["t"] for x in r], unit="ms").normalize()
    C[s] = pd.Series([x["c"] for x in r], index=t); V[s] = pd.Series([x["v"] for x in r], index=t)
Cl = pd.DataFrame(C).sort_index(); Vo = pd.DataFrame(V).reindex(Cl.index)
dv = (Cl * Vo).rolling(60, min_periods=40).median(); ok = Cl.notna() & (Cl >= 10) & (dv >= 25e6) & (Cl.notna().cumsum() >= 260)
R1 = Cl.pct_change(fill_method=None)
mkt = R1.where(ok).mean(axis=1).fillna(0); idx = (1 + mkt).cumprod(); slab = idx < idx.rolling(50).mean()
dates = list(range(260, len(Cl) - 22, 5))
out = {"bumag": Cl.shape[1], "sessiy": len(Cl), "dat": len(dates)}
def spread(L, H, rezhim=None):
    vals = []
    for i in dates:
        if rezhim is not None and bool(slab.iloc[i]) != rezhim: continue
        m = ok.iloc[i]
        past = Cl.iloc[i] / Cl.iloc[i - L] - 1 if L != 231 else Cl.iloc[i - 21] / Cl.iloc[i - 252] - 1
        fwd = Cl.iloc[i + H] / Cl.iloc[i] - 1
        x = pd.DataFrame({"p": past, "f": fwd})[m].dropna()
        if len(x) < 50: continue
        top = x[x.p >= x.p.quantile(0.9)]
        vals.append(top.f.mean() - x.f.mean())
    step = max(1, H // 5)                                 # непересекающиеся даты для t
    v = np.array(vals[::step]) if vals else np.array([0.0])
    return dict(n=len(v), spred_pct=round(float(np.mean(vals)) * 100, 3) if vals else None,
                t=round(float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))), 2) if len(v) > 2 else None)
for L in (5, 21, 63, 126, 231):
    for H in (5, 21):
        out[f"L{L}_H{H}"] = spread(L, H)
for L in (5, 126, 231):
    for H in (5, 21):
        out[f"L{L}_H{H}_rynok_slab"] = spread(L, H, True); out[f"L{L}_H{H}_rynok_silen"] = spread(L, H, False)
out["dolya_slabogo_rynka"] = round(float(slab.iloc[dates].mean()), 3)
Path("results/alpaca_diag_20261026/gorizont.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
