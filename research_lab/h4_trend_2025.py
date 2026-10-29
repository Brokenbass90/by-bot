#!/usr/bin/env python3
"""h4_trend_2025.py — prereg/PREREG_H4_TREND_2025_2026_10_29.md. Только чтение кэша.  python3 research_lab/h4_trend_2025.py"""
import collections, glob, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
SHA = "02ee48e3006fe9c80c7412c030a2212dd61172faee38fd8a30b4ad5a51fb316a"; H4, DEN = 4 * 3600000, 86400000; OT, DO = 1738368000000, 1759276800000; KOM = 0.002

def agg(b, ms):
    g = collections.OrderedDict()
    for x in b: g.setdefault(x[0] // ms * ms, []).append(x)
    return [[t, v[0][1], max(y[2] for y in v), min(y[3] for y in v), v[-1][4]] for t, v in g.items() if len(v) == ms // 3600000]

def ema(xs, n):
    k, e, out = 2 / (n + 1), None, []
    for x in xs: e = x if e is None else e + k * (x - e); out.append(e)
    return out

def rsi(c, n=14):
    out = [None] * len(c); g = l = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]; g = (g * (n - 1) + max(d, 0)) / n; l = (l * (n - 1) + max(-d, 0)) / n
        if i >= n: out[i] = 100 - 100 / (1 + g / l) if l > 0 else 100
    return out

def atr(b, n=14):
    out = [None] * len(b); tr = []
    for i in range(1, len(b)):
        tr.append(max(b[i][2] - b[i][3], abs(b[i][2] - b[i - 1][4]), abs(b[i][3] - b[i - 1][4])))
        if len(tr) >= n: out[i] = sum(tr[-n:]) / n
    return out

def sdelka(b, j, side, risk):
    e = b[j][1]; stop = e - side * 2 * risk; tg = e + side * 3 * 2 * risk
    for k in range(j, min(len(b), j + 30)):
        if (side > 0 and b[k][3] <= stop) or (side < 0 and b[k][2] >= stop): r = -1.0; break
        if (side > 0 and b[k][2] >= tg) or (side < 0 and b[k][3] <= tg): r = 3.0; break
    else:
        k = min(len(b), j + 30) - 1; r = (b[k][4] - e) * side / (2 * risk)
    kom = KOM * e / (2 * risk); return r - kom, kom, k

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_H4_TREND_2025_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    rng = random.Random(20261029); sd = []
    for p in sorted(glob.glob(str(HERE / "data" / "flet_2025_kesh" / "*.json"))):
        b1 = json.load(open(p))
        if len(b1) < 2000: continue
        b = agg(b1, H4); d = agg(b1, DEN)
        if len(b) < 300 or len(d) < 40: continue
        ed = ema([x[4] for x in d], 20); dt = {d[i][0]: (ed[i - 1] - ed[i - 6]) if i >= 6 else 0 for i in range(len(d))}
        A = atr(b); R = rsi([x[4] for x in b]); zan = {"A": -1, "B": -1, "C": -1}
        def trend(t): return 1 if dt.get(t // DEN * DEN, 0) > 0 else (-1 if dt.get(t // DEN * DEN, 0) < 0 else 0)
        def kontrol(side, risk_pct):
            cs = []
            for _ in range(5):
                j = rng.randrange(30, len(b) - 31)
                if not (OT <= b[j][0] < DO): continue
                r, _, _ = sdelka(b, j, side, b[j][1] * risk_pct); cs.append(r)
            return st.mean(cs) if cs else None
        def zap(ruka, i, j, side):
            if j >= len(b) - 1 or A[i] is None or j <= zan[ruka]: return
            r, kom, k = sdelka(b, j, side, A[i]); zan[ruka] = k
            sd.append(dict(ruka=ruka, sym=Path(p).stem, ts=b[j][0], side=side, R=r, kom=kom, ctrl=kontrol(side, A[i] / b[j][1])))
        for i in range(25, len(b) - 32):
            if not (OT <= b[i][0] < DO) or A[i] is None: continue
            tr = trend(b[i][0])
            if tr == 0: continue
            hi20 = max(x[2] for x in b[i - 20:i]); lo20 = min(x[3] for x in b[i - 20:i])
            if (tr > 0 and b[i][4] > hi20) or (tr < 0 and b[i][4] < lo20):
                zap("A", i, i + 1, tr); ur = hi20 if tr > 0 else lo20
                for k in range(i + 1, min(len(b) - 2, i + 7)):
                    if (tr > 0 and b[k][3] <= ur and b[k][4] > ur) or (tr < 0 and b[k][2] >= ur and b[k][4] < ur): zap("B", i, k + 1, tr); break
            if R[i] is not None and ((tr > 0 and R[i] < 40) or (tr < 0 and R[i] > 60)):
                for k in range(i + 1, min(len(b) - 2, i + 3)):
                    if (tr > 0 and b[k][2] > b[i][2]) or (tr < 0 and b[k][3] < b[i][3]): zap("C", i, k, tr); break
    out = {}
    for ruka in "ABC":
        g = [x for x in sd if x["ruka"] == ruka and x["ctrl"] is not None]
        if not g: out[ruka] = dict(n=0); continue
        po = collections.defaultdict(list); mes = collections.defaultdict(float)
        for x in g: po[time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))].append(x["R"] - x["ctrl"]); mes[time.strftime("%Y-%m", time.gmtime(x["ts"] / 1000))] += x["R"] * 10
        m = [st.mean(v) for v in po.values()]; t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
        eq = pk = dd = 0
        for x in sorted(g, key=lambda x: x["ts"]): eq += x["R"]; pk = max(pk, eq); dd = max(dd, pk - eq)
        o = dict(n=len(g), monet=len({x["sym"] for x in g}), R=round(st.mean(x["R"] for x in g), 4), kontrol=round(st.mean(x["ctrl"] for x in g), 4),
                 vklad=round(st.mean(x["R"] - x["ctrl"] for x in g), 4), t_dni=round(t, 2) if t else None, kom_R=round(st.mean(x["kom"] for x in g), 3),
                 vyigr=round(sum(x["R"] > 0 for x in g) / len(g), 3), mesyacy_usd_pri_10={k: round(v, 1) for k, v in sorted(mes.items())},
                 mesyacev_plus=sum(v > 0 for v in mes.values()), prosadka_R=round(dd, 1))
        o["vyvod"] = "PASS_V_TEN" if o["n"] >= 150 and o["R"] > 0 and o["vklad"] > 0 and (t or 0) >= 2.4 and o["mesyacev_plus"] >= 5 else "FAIL"
        out[ruka] = o
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("h4_trend_2025_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(out, sdelki=sd), ensure_ascii=False))

if __name__ == "__main__":
    main()
