#!/usr/bin/env python3
"""inplay_etap2.py — этап 2 восстановления InPlay (21.10.2026): вход отдельно от ведения + 3 контекстных замера.
Диагностика на сделках v4 из прогонов этапа 1 (results/inplay_vosstanovlenie_20261021). Параметры не подбираются:
горизонты 12/24 ч и терцили заданы заранее. Единица — ATR(14) часовой на момент входа (не зависит от стопа).
Вход: fwd_H = сторона·(close[t+H] − entry)/ATR. Контроль: случайные входы той же монеты, той же стороны, того же
периода прогона (seed фиксирован). Ведение: фактический R сделки против нейтрального выхода через 24 ч.
Замеры: Z1 режим BTC (close vs EMA200 H1 и наклон 24 ч) × сторона; Z2 «в игре» — объём 24 ч / медиана суточного
за 30 дн (терцили); Z3 сжатие перед входом — диапазон 48 ч / ATR (терцили)."""
import csv, glob, json, math, random, statistics as st, sys
from pathlib import Path
LAB = Path(__file__).resolve().parent; ROOT = LAB.parent
RES = LAB / "results" / "inplay_vosstanovlenie_20261021"
H = 3_600_000; random.seed(20261021)

def chasy(sym):
    m = {}
    for f in glob.glob(str(ROOT / ".cache" / "klines" / f"{sym}_5_*.json")):
        d = json.load(open(f)); rows = d if isinstance(d, list) else d["records"]
        for r in rows:
            t = int(r[0]) // H * H; o, h, l, c, v = map(float, r[1:6])
            x = m.get(t)
            if x is None or int(r[0]) < x[5]: pass
            if x is None: m[t] = [o, h, l, c, v, int(r[0]), int(r[0])]
            else:
                x[1] = max(x[1], h); x[2] = min(x[2], l); x[4] += v
                if int(r[0]) >= x[6]: x[3] = c; x[6] = int(r[0])
                if int(r[0]) <= x[5]: x[0] = o; x[5] = int(r[0])
    ts = sorted(m); return ts, [m[t] for t in ts]

def atr(b, i, n=14):
    if i < n + 1: return None
    return sum(max(b[k][1] - b[k][2], abs(b[k][1] - b[k - 1][3]), abs(b[k][2] - b[k - 1][3])) for k in range(i - n, i)) / n

def ema(xs, n):
    a = 2 / (n + 1); out = []; e = xs[0]
    for x in xs: e = a * x + (1 - a) * e; out.append(e)
    return out

PROGONY = {"d_S7_290": "S7 шорт", "d_S7_long": "S7 лонг+шорт", "d_S7_pre": "S7 до окна", "d_O9_long": "9 других",
           "d_BE_old_long": "BTC+ETH 2023-25"}
sdelki, vid = [], set()
for p, nm in PROGONY.items():
    for r in csv.DictReader(open(RES / f"{p}_trades.csv")):
        k = (r["symbol"], r["side"], r["entry_ts"])
        if k in vid: continue                       # дубли между прогонами (S7 шорт ⊂ S7 лонг+шорт) — один раз
        vid.add(k); sdelki.append(dict(r, progon=p))
syms = sorted({s["symbol"] for s in sdelki} | {"BTCUSDT"})
B = {s: chasy(s) for s in syms}
bt, bb = B["BTCUSDT"]; bidx = {t: i for i, t in enumerate(bt)}; e200 = ema([x[3] for x in bb], 200)

def kontekst(sym, t):
    ts, b = B[sym]; idx = {}
    return None

out = []
for s in sdelki:
    ts, b = B[s["symbol"]]
    t0 = int(s["entry_ts"]) // H * H
    try: i = ts.index(t0)
    except ValueError: continue
    a = atr(b, i)
    if not a or i + 25 >= len(b) or i < 720: continue
    sd = 1 if s["side"] == "long" else -1; e = float(s["entry_price"])
    f12 = sd * (b[i + 12][3] - e) / a; f24 = sd * (b[i + 24][3] - e) / a
    fakt = sd * (float(s["exit_price"]) - e) / a
    j = bidx.get(t0)
    rez = None
    if j and j >= 224: rez = "UP" if bb[j - 1][3] > e200[j - 1] and e200[j - 1] > e200[j - 25] else ("DOWN" if bb[j - 1][3] < e200[j - 1] and e200[j - 1] < e200[j - 25] else "FLAT")
    v24 = sum(x[4] for x in b[i - 24:i]); dn = sorted(sum(x[4] for x in b[k - 24:k]) for k in range(i - 720, i, 24))
    vrel = v24 / dn[len(dn) // 2] if dn[len(dn) // 2] > 0 else None
    szh = (max(x[1] for x in b[i - 48:i]) - min(x[2] for x in b[i - 48:i])) / a
    # контроль: 5 случайных часов того же прогона/монеты/стороны
    lo = i - 24 * 60; ctr = []
    for _ in range(5):
        k = random.randint(max(720, lo), len(b) - 26); ak = atr(b, k)
        if ak: ctr.append(sd * (b[k + 24][3] - b[k][0]) / ak)
    out.append(dict(progon=s["progon"], sym=s["symbol"], side=s["side"], f12=f12, f24=f24, fakt=fakt, ctr=st.mean(ctr) if ctr else None,
                    rezhim=rez, soglasno=(rez == "UP" and sd == 1) or (rez == "DOWN" and sd == -1) if rez else None,
                    vrel=vrel, szh=szh, pnl=float(s["pnl"])))

def svod(g):
    g = [x for x in g if x["ctr"] is not None]
    if len(g) < 8: return f"n={len(g)}"
    d = [x["f24"] - x["ctr"] for x in g]; sd = st.stdev(d) or 1
    return (f"n={len(g)} вход24={st.mean(x['f24'] for x in g):+.3f} контроль={st.mean(x['ctr'] for x in g):+.3f} "
            f"эдж={st.mean(d):+.3f} t={st.mean(d)/(sd/math.sqrt(len(d))):+.2f} | факт={st.mean(x['fakt'] for x in g):+.3f} "
            f"нейтр24={st.mean(x['f24'] for x in g):+.3f}")

def tercili(key):
    v = sorted(x[key] for x in out if x[key] is not None); return v[len(v) // 3], v[2 * len(v) // 3]

rep = {"vsego": svod(out)}
for p in PROGONY: rep[f"progon {PROGONY[p]}"] = svod([x for x in out if x["progon"] == p])
for sd in ("long", "short"): rep[f"сторона {sd}"] = svod([x for x in out if x["side"] == sd])
for k in ("UP", "DOWN", "FLAT"): rep[f"Z1 режим BTC {k}"] = svod([x for x in out if x["rezhim"] == k])
rep["Z1 по режиму"] = svod([x for x in out if x["soglasno"] is True]); rep["Z1 против режима"] = svod([x for x in out if x["soglasno"] is False])
a, b_ = tercili("vrel"); rep["Z2 пороги"] = f"{a:.2f} / {b_:.2f}"
rep["Z2 объём низкий"] = svod([x for x in out if x["vrel"] is not None and x["vrel"] <= a])
rep["Z2 объём средний"] = svod([x for x in out if x["vrel"] is not None and a < x["vrel"] <= b_])
rep["Z2 объём высокий (в игре)"] = svod([x for x in out if x["vrel"] is not None and x["vrel"] > b_])
a, b_ = tercili("szh"); rep["Z3 пороги ATR"] = f"{a:.1f} / {b_:.1f}"
rep["Z3 сжатие сильное"] = svod([x for x in out if x["szh"] <= a])
rep["Z3 среднее"] = svod([x for x in out if a < x["szh"] <= b_])
rep["Z3 широкий диапазон"] = svod([x for x in out if x["szh"] > b_])
(LAB / "results" / "inplay_etap2_20261021.json").write_text(json.dumps({"svod": rep, "sdelki": out}, ensure_ascii=False, indent=0))
print("\n".join(f"{k}: {v}" for k, v in rep.items()))
