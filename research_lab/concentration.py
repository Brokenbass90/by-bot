#!/usr/bin/env python3
"""concentration.py — не держится ли результат на нескольких монетах и сделках.

Одна большая цифра может быть эджем, а может быть двумя монетами, которые
рухнули. Проверяем три вещи:
    сколько монет в плюсе из всех задействованных;
    сколько дают верхние 5% сделок;
    что остаётся, если их убрать.
"""
import sys, os, glob, collections
import numpy as np
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "research_lab")
import importlib
from research_machine import simulate, Store, ema

MOD, CLS, PFX, SIDE = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
MULT, HOLD, REG = float(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
CD = sys.argv[8] if len(sys.argv) > 8 else "0"
W = {"2024-03..2025-09": (1709251200000, 1759276800000),
     "2023-01..2024-02": (1672531200000, 1709251200000)}

files = sorted(glob.glob("research_lab/data/h1/*.npz"))
os.environ.update({f"{PFX}_SYMBOL_ALLOWLIST": ",".join(Path(f).stem for f in files),
                   f"{PFX}_ALLOW_LONGS": "1", f"{PFX}_ALLOW_SHORTS": "1"})
if CD != "0":
    os.environ[f"{PFX}_COOLDOWN_BARS_5M"] = CD
S = getattr(importlib.import_module(f"strategies.{MOD}"), CLS)
d = np.load("research_lab/data/h1/BTCUSDT.npz")
c = d["ohlcv"][:, 3].astype(float); e = ema(c, 200)
bts, bd = d["ts"], (c - e) / e


def ok(t):
    if REG == "любой":
        return True
    j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
    v = float(bd[j]) if j < len(bd) else 0.0
    return {"флет-": -0.02 <= v < 0, "флет+": 0 <= v < 0.02,
            "падает": v < 0, "растёт": v >= 0}[REG]


tr = {w: [] for w in W}
for k, fp in enumerate(files):
    dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
    m = ts < 1759276800000
    ts, o = ts[m], o[m]
    if len(ts) < 420:
        continue
    bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]] for x in range(len(ts))]
    st = Store(Path(fp).stem); strat = S(); block = -1
    for i in range(120, len(bars) - 1):
        st.rows = bars[: i + 1]; b = bars[i]
        try:
            s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
        except Exception:
            continue
        if s is None or s.side != SIDE or i <= block or not ok(b[0]):
            continue
        r = simulate(bars, i, SIDE, s.sl, list(s.tps or []),
                     (s.tp_fracs or [0.55])[0], MULT, HOLD)
        if r is None:
            continue
        block = i + r["bars"] + 1
        for w, (a, b2) in W.items():
            if a <= b[0] < b2:
                tr[w].append((Path(fp).stem, r["R"]))
    if (k + 1) % 40 == 0:
        print(f"... {k+1}/{len(files)}", flush=True)

print(f"\n{PFX} {SIDE} ×{MULT} {HOLD}ч режим «{REG}»")
for w in W:
    t = tr[w]
    if len(t) < 30:
        print(f"{w}: сделок мало"); continue
    R = np.array([x[1] for x in t])
    pnl = collections.defaultdict(float)
    for s, r in t:
        pnl[s] += r
    srt = np.sort(R)[::-1]; k5 = max(1, len(R) // 20)
    print(f"\n{w}: сделок {len(R)}, итог {R.sum():+.1f}R, среднее {R.mean():+.4f}R, "
          f"медиана {np.median(R):+.4f}R")
    print(f"  монет задействовано {len(pnl)}, в плюсе {sum(1 for v in pnl.values() if v > 0)}")
    print(f"  верхние 5% сделок ({k5}) дают {srt[:k5].sum():+.1f}R из {R.sum():+.1f}R")
    print(f"  без них среднее {srt[k5:].mean():+.4f}R")
    top = sorted(pnl.items(), key=lambda x: -x[1])[:5]
    print(f"  топ-5 монет: {[(s, round(v,1)) for s,v in top]} = {sum(v for _,v in top):+.1f}R")
