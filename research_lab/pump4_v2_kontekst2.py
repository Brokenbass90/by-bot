import glob, json, math, datetime as dt
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); T1 = int(dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc).timestamp() * 1000)
def ema(x, n):
    k = 2 / (n + 1); out = np.empty(len(x)); e = x[0]
    for i, v in enumerate(x): e = v * k + e * (1 - k); out[i] = e
    return out
ev = []
for f in sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz"))):
    d = np.load(f); ts = d["ts"].astype(np.int64); a = d["ohlcv"].astype(float); h, l, c = a[:, 1], a[:, 2], a[:, 3]
    e720 = ema(c, 720); n = len(c); pauza = -1; prosh = []
    for t in range(744, n - 168):
        if ts[t] < T0 or ts[t] > T1 or t < pauza: continue
        P = h[t - 23:t + 1].max()
        if c[t] / c[t - 24] - 1 < 0.15 or c[t] < 0.97 * P: continue
        pauza = t + 72; L = l[t - 23:t + 1].min(); cel = P - 0.5 * (P - L); skv = 1.05 * P; ish = "NEYASNO"
        for j in range(t + 1, t + 169):
            a_, b_ = l[j] <= cel, h[j] >= skv
            if a_ and b_: break
            if a_: ish = "OTKAT"; break
            if b_: ish = "SKVIZ"; break
        g1 = "da" if c[t - 24] > e720[t - 24] else "net"          # тренд до пампа (до его начала)
        g2 = "da" if any(t - p <= 14 * 24 for p in prosh) else "net"; prosh.append(t)
        ev.append(dict(god=dt.datetime.utcfromtimestamp(ts[t] / 1000).year, ish=ish, G1=g1, G2=g2))
def dolya(g):
    r = [e for e in g if e["ish"] != "NEYASNO"]; return (sum(e["ish"] == "OTKAT" for e in r) / len(r) if r else None), len(r)
out = {"sobytiy": len(ev), "vse": dolya(ev), "filtry": {}}
for F in ("G1", "G2"):
    pa, na = dolya([e for e in ev if e[F] == "da"]); pn, nn = dolya([e for e in ev if e[F] == "net"])
    p = (pa * na + pn * nn) / (na + nn); z = (pa - pn) / math.sqrt(p * (1 - p) * (1 / na + 1 / nn)); d = (pa - pn) * 100
    goda = {y: (lambda a1, b1: None if a1 is None or b1 is None else round((a1 - b1) * 100, 1))(dolya([e for e in ev if e[F] == "da" and e["god"] == y])[0], dolya([e for e in ev if e[F] == "net" and e["god"] == y])[0]) for y in (2023, 2024, 2025, 2026)}
    znak = sum(1 for g in goda.values() if g is not None and (g > 0) == (d > 0))
    out["filtry"][F] = dict(da=(round(pa, 3), na), net=(round(pn, 3), nn), raznica_pp=round(d, 2), z=round(z, 2), po_godam=goda, v_V2=bool(abs(d) >= 5 and abs(z) >= 2 and znak >= 3))
(LAB / "results" / "pump4_v2_kontekst2_20261020.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False))
