#!/usr/bin/env python3
"""flet_setka.py — prereg/PREREG_FLET_SETKA_2026_10_29.md. Только чтение кэша H1.  python3 research_lab/flet_setka.py"""
import collections, glob, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import retest_sloped as RS
SHA = "ea1ec9e30bcf15ad043fc523489d8a3fec65d37b36a33e8d6b8274d62256805b"; KOM = 0.002

def flet(b, i):
    w = b[i - 168:i + 1]; hi = max(x[2] for x in w); lo = min(x[3] for x in w); mid = (hi + lo) / 2; rg = hi - lo
    if rg <= 0 or rg / mid > 0.12 or abs(b[i][4] / b[i - 168][4] - 1) > 0.03: return None
    if sum(x[2] >= hi - 0.1 * rg for x in w) < 2 or sum(x[3] <= lo + 0.1 * rg for x in w) < 2: return None
    if sum(x[5] * x[4] for x in b[i - 23:i + 1]) < 2e6: return None
    return lo, hi

def setka(b, i, lo, hi, side):
    rg = hi - lo; mid = (lo + hi) / 2; chasti = []
    for k in range(i + 1, min(len(b), i + 73)):
        o, h, l, c = b[k][1:5]
        if not chasti:
            if (side > 0 and c <= lo + 0.25 * rg) or (side < 0 and c >= hi - 0.25 * rg): chasti.append(c)
            elif k - i > 24: return None, k                      # не дождались входа за сутки
            continue
        if (side > 0 and c < lo * 0.97) or (side < 0 and c > hi * 1.03): return vyhod(chasti, c, side), k
        if (side > 0 and h >= mid) or (side < 0 and l <= mid): return vyhod(chasti, mid, side), k
        if len(chasti) < 5 and ((side > 0 and c <= chasti[0] * (1 - 0.01 * len(chasti))) or (side < 0 and c >= chasti[0] * (1 + 0.01 * len(chasti)))): chasti.append(c)
    if not chasti: return None, i + 24
    k = min(len(b), i + 73) - 1; return vyhod(chasti, b[k][4], side), k

def vyhod(chasti, px, side):
    return sum(((px / p - 1) * side - KOM) / 10 for p in chasti) * 100          # % от депозита сетки (10 частей)

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_FLET_SETKA_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    rng = random.Random(20261029); sd = []
    for p in sorted(glob.glob(str(HERE / "data" / "h1_kesh_att1" / "*.json"))):
        b = RS.bary(p)
        if len(b) < 300: continue
        b = [x if len(x) >= 6 else x + [0] for x in b]
        ne_flet = [i for i in range(170, len(b) - 80, 6) if flet(b, i) is None]
        for side in (1, -1):
            zan = 0
            for i in range(170, len(b) - 80):
                if i <= zan: continue
                f = flet(b, i)
                if not f: continue
                r, k = setka(b, i, f[0], f[1], side)
                if r is None: zan = k; continue
                cs = []
                for _ in range(5):
                    if not ne_flet: break
                    j = rng.choice(ne_flet); w = b[j - 168:j + 1]; c = b[j][4]; rg = c * (f[1] - f[0]) / ((f[0] + f[1]) / 2)
                    rc, _ = setka(b, j, c - rg / 2 if side > 0 else c - rg / 2, c + rg / 2, side)
                    if rc is not None: cs.append(rc)
                sd.append(dict(sym=Path(p).stem, ts=b[i][0], side=side, pct=round(r, 3), ctrl=st.mean(cs) if cs else None)); zan = k
    def svod(g):
        g = [x for x in g if x["ctrl"] is not None]
        if not g: return dict(n=0)
        po = collections.defaultdict(list)
        for x in g: po[time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))].append(x["pct"] - x["ctrl"])
        m = [st.mean(v) for v in po.values()]; t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
        return dict(n=len(g), monet=len({x["sym"] for x in g}), sred_pct=round(st.mean(x["pct"] for x in g), 3), kontrol=round(st.mean(x["ctrl"] for x in g), 3),
                    raznica=round(st.mean(x["pct"] - x["ctrl"] for x in g), 3), t_dni=round(t, 2) if t else None, vyigr=round(sum(x["pct"] > 0 for x in g) / len(g), 3),
                    hudshaya=round(min(x["pct"] for x in g), 2), dney=len(m))
    out = dict(long=svod([x for x in sd if x["side"] > 0]), short=svod([x for x in sd if x["side"] < 0]), vse=svod(sd))
    v = out["vse"]; out["vyvod"] = "PASS_V_PROVERKU_2025" if v.get("n", 0) >= 100 and v["sred_pct"] > 0 and v["raznica"] > 0 and (v["t_dni"] or 0) >= 2 else "FAIL"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("flet_setka_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(out, setki=sd), ensure_ascii=False))

if __name__ == "__main__":
    main()
