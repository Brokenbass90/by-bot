"""Конвертер m5 preholdout (bybit_wide137_m5, 2024-03…2025-09) → 15m npz в формате data/h1 (ts, ohlcv, nsub).
15m собирается по календарным границам из ПОЛНЫХ трёх 5m-баров (неполный бар отбрасывается). Только < 2025-10-01."""
import json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
SRC = LAB / "data/bybit_wide137_m5_preholdout_20240301_20250930"; OUT = LAB / "os2/dannye_15m"; M15 = 900000
def one(sym):
    f = OUT / f"{sym}.npz"
    if f.exists(): return "uzhe"
    rec = json.loads((SRC / sym / f"{sym}.json").read_text())["records"]
    b = {}
    for r in rec:
        t = int(r["ts_ms"])
        if t >= 1759276800000: continue
        k = t // M15 * M15; b.setdefault(k, []).append(r)
    ts, o, n = [], [], []
    for k in sorted(b):
        g = sorted(b[k], key=lambda r: r["ts_ms"])
        if len(g) != 3: continue
        ts.append(k); o.append([g[0]["open"], max(x["high"] for x in g), min(x["low"] for x in g), g[-1]["close"], sum(x["volume"] for x in g)]); n.append(3)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez(f, ts=np.array(ts, dtype=np.int64), ohlcv=np.array(o, dtype=float), nsub=np.array(n)); return len(ts)
if __name__ == "__main__":
    syms = sys.argv[1:] or sorted(p.name for p in SRC.iterdir() if p.is_dir())
    for s in syms: print(s, one(s), flush=True)
