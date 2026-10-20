#!/usr/bin/env python3
"""PREREG_PUMP4_OI_DINAMIKA_2026_10_20. Запуск у владельца (нужна сеть Bybit): .venv/bin/python3 research_lab/pump4_oi_zamer.py
Кэш OI: research_lab/data/bybit_oi_1h/<SYM>.json (дописывается). Итог: research_lab/results/pump4_oi_20261020.json"""
import glob, json, math, os, time, urllib.request, datetime as dt
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent; H = 3600_000
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); T1 = int(dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc).timestamp() * 1000)
KESH = LAB / "data" / "bybit_oi_1h"; KESH.mkdir(parents=True, exist_ok=True)
def oi_okno(sym, t):
    """OI на t и t−24 ч (закрытые часы) — один запрос на событие, кэшируется."""
    p = KESH / f"{sym}.json"; kesh = json.loads(p.read_text()) if p.exists() else {}
    k = str(t)
    if k not in kesh:
        u = (f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol={sym}&intervalTime=1h"
             f"&startTime={t - 26 * H}&endTime={t}&limit=50")
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "oi/1.0"}), timeout=20) as f:
                lst = ((json.loads(f.read().decode()).get("result") or {}).get("list") or [])
            ser = {int(x["timestamp"]): float(x["openInterest"]) for x in lst}
            a, b = ser.get(t), ser.get(t - 24 * H)
            kesh[k] = [a, b]
        except Exception:
            kesh[k] = None
        p.write_text(json.dumps(kesh)); time.sleep(0.08)
    return kesh[k]
ev = []
for f in sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz"))):
    sym = Path(f).stem
    if "_B21" in sym: continue
    d = np.load(f); ts = d["ts"].astype(np.int64); a = d["ohlcv"].astype(float); h, l, c = a[:, 1], a[:, 2], a[:, 3]
    pauza = -1
    for t in range(744, len(c) - 168):
        if ts[t] < T0 or ts[t] > T1 or t < pauza: continue
        P = h[t - 23:t + 1].max()
        if c[t] / c[t - 24] - 1 < 0.15 or c[t] < 0.97 * P: continue
        pauza = t + 72; L = l[t - 23:t + 1].min(); cel = P - 0.5 * (P - L); skv = 1.05 * P; ish = "NEYASNO"
        for j in range(t + 1, t + 169):
            a_, b_ = l[j] <= cel, h[j] >= skv
            if a_ and b_: break
            if a_: ish = "OTKAT"; break
            if b_: ish = "SKVIZ"; break
        oi = oi_okno(sym, int(ts[t]))
        doi = (oi[0] / oi[1] - 1) if oi and oi[0] and oi[1] else None
        ev.append(dict(sym=sym, god=dt.datetime.utcfromtimestamp(ts[t] / 1000).year, ish=ish, doi=doi))
    print(sym, len(ev), flush=True)
def dolya(g):
    r = [e for e in g if e["ish"] != "NEYASNO"]; return (sum(e["ish"] == "OTKAT" for e in r) / len(r) if r else None), len(r)
pokr = sum(e["doi"] is not None for e in ev) / max(1, len(ev))
out = dict(sobytiy=len(ev), pokrytie_oi=round(pokr, 3))
if pokr < 0.7:
    out["verdikt"] = "BLOCKED_DATA"
else:
    da = [e for e in ev if e["doi"] is not None and e["doi"] >= 0.20]; net = [e for e in ev if e["doi"] is not None and e["doi"] <= 0]
    pa, na = dolya(da); pn, nn = dolya(net)
    p = (pa * na + pn * nn) / (na + nn); z = (pa - pn) / math.sqrt(p * (1 - p) * (1 / na + 1 / nn)); dpp = (pa - pn) * 100
    goda = {y: (lambda x, y_: None if x is None or y_ is None else round((x - y_) * 100, 1))(dolya([e for e in da if e["god"] == y])[0], dolya([e for e in net if e["god"] == y])[0]) for y in (2023, 2024, 2025, 2026)}
    znak = sum(1 for g in goda.values() if g is not None and (g > 0) == (dpp > 0))
    out.update(oi_rost=(round(pa, 3), na), oi_padenie=(round(pn, 3), nn), raznica_pp=round(dpp, 2), z=round(z, 2), po_godam=goda,
               v_V2=bool(abs(dpp) >= 5 and abs(z) >= 2 and znak >= 3),
               mediana_doi=round(float(np.median([e["doi"] for e in ev if e["doi"] is not None])), 3))
(LAB / "results" / "pump4_oi_20261020.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False))
