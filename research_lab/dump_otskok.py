#!/usr/bin/env python3
"""dump_otskok.py — prereg/PREREG_DUMP_OTSKOK_2026_10_28.md. Только чтение кэша H1.  python3 research_lab/dump_otskok.py"""
import collections, glob, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import retest_sloped as RS
SHA = "41de7f75898253475026e14f43bc756ff14c954258f83d52f60e79261f1ec665"; KOM = 0.002

def atr(b, i): return RS.atr(b, i)

def vyhod(b, j, stop, risk):
    e = b[j][1]; tg = e + 1.5 * risk
    for k in range(j, min(len(b), j + 48)):
        if b[k][3] <= stop: return -1.0, k
        if b[k][2] >= tg: return 1.5, k
    k = min(len(b), j + 48) - 1; return (b[k][4] - e) / risk, k

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_DUMP_OTSKOK_2026_10_28.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    rng = random.Random(20261028); ev = []
    for p in sorted(glob.glob(str(HERE / "data" / "h1_kesh_att1" / "*.json"))):
        b = RS.bary(p)
        if len(b) < 200: continue
        zan = -1
        for i in range(72, len(b) - 50):
            if i <= zan: continue
            c = b[i][4]
            if not c / b[i - 24][4] - 1 <= -0.08: continue
            if not (b[i][4] > b[i][1] and all(b[k][4] <= b[k][1] for k in range(i - 5, i))): continue
            lo = min(x[3] for x in b[i - 23:i + 1])
            if not c > lo: continue
            a = atr(b, i)
            if not (a == a and a > 0): continue
            e = b[i + 1][1]; stop = lo - 0.3 * a; risk = e - stop
            if risk <= 0: continue
            r, k = vyhod(b, i + 1, stop, risk); kom = KOM * e / risk
            ctrl = []
            for _ in range(5):
                j = rng.randrange(72, len(b) - 50); aj = atr(b, j)
                if not (aj == aj and aj > 0): continue
                ej = b[j][1]; rj = risk / a * aj; rr, _ = vyhod(b, j, ej - rj, rj); ctrl.append(rr - KOM * ej / rj)
            ev.append(dict(sym=Path(p).stem, ts=b[i + 1][0], R=r - kom, ctrl=st.mean(ctrl) if ctrl else None, stop_pct=risk / e * 100, stop_atr=risk / a, kom=kom))
            zan = k
    g = [x for x in ev if x["ctrl"] is not None]
    po = collections.defaultdict(list)
    for x in g: po[time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))].append(x["R"] - x["ctrl"])
    m = [st.mean(v) for v in po.values()]; t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
    zam = dict(signalov=len(ev), monet=len({x["sym"] for x in ev}), stop_pct_med=round(st.median(x["stop_pct"] for x in ev), 2),
               stop_atr_med=round(st.median(x["stop_atr"] for x in ev), 2), kom_R_med=round(st.median(x["kom"] for x in ev), 3))
    print("ЗАМЕРЫ:", zam)
    out = dict(n=len(g), dney=len(m), R=round(st.mean(x["R"] for x in g), 4), kontrol=round(st.mean(x["ctrl"] for x in g), 4),
               vklad=round(st.mean(x["R"] - x["ctrl"] for x in g), 4), t_dni=round(t, 2) if t else None, vyigr=round(sum(x["R"] > 0 for x in g) / len(g), 3))
    ok = out["n"] >= 60 and out["R"] > 0 and out["vklad"] > 0 and (out["t_dni"] or 0) >= 2
    print("PnL:", out, "ВЕРДИКТ:", "PASS_V_TEN" if ok else "FAIL")
    (HERE / "results" / time.strftime("dump_otskok_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(zamery=zam, pnl=out, vyvod="PASS_V_TEN" if ok else "FAIL", sobytiya=ev), ensure_ascii=False))

if __name__ == "__main__":
    main()
