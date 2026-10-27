#!/usr/bin/env python3
"""retest_sloped.py — prereg/PREREG_RETEST_SLOPED_2026_10_27.md. Только чтение кэша H1. python3 research_lab/retest_sloped.py"""
import collections, glob, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent))
import bot.market_context as mc
SHA = "501cbfd22eb728cc378444c1b1558e5ebab7c7e42085feebbccf78a7dad93ebc"; KOM = 0.002; H = 3600000

def bary(p):
    d = json.load(open(p)); d = d if isinstance(d, list) else (d.get("h1") or [])
    return [[int(x[0])] + [float(v) for v in x[1:6]] for x in sorted(d)]

def atr(b, i): return mc.atr([[x[0], x[1], x[2], x[3], x[4], x[5]] for x in b[i - 15:i]], 14)

def progon(b, j, side, stop, risk):
    e = b[j][1]; tg = e - 2 * risk if side == "short" else e + 2 * risk
    for k in range(j, min(len(b), j + 24)):
        if side == "short":
            if b[k][2] >= stop: return -1.0, k
            if b[k][3] <= tg: return 2.0, k
        else:
            if b[k][3] <= stop: return -1.0, k
            if b[k][2] >= tg: return 2.0, k
    k = min(len(b), j + 24) - 1
    return ((e - b[k][4]) if side == "short" else (b[k][4] - e)) / risk, k

def sobytiya(s, b, proboy_atr=0.1, min_do_retesta=1, obem_x=0.0):
    out = []; zanyato = {"short": -1, "long": -1}
    for i in range(130, len(b) - 30):
        a = atr(b, i)
        if not (a == a and a > 0): continue
        for side, lside in (("short", "support"), ("long", "resistance")):
            if i <= zanyato[side]: continue
            w = b[i - 120:i]; sl = mc.sloped_level([[x[0], x[1], x[2], x[3], x[4], x[5]] for x in w], side=lside, left=2, right=2, min_pivots=2, last_pivots=3)
            if sl is None or not sl["valid"]: continue
            L = lambda k, sl=sl, i=i: sl["intercept"] + sl["slope"] * (k - (i - 120))
            if side == "short" and not b[i][4] < L(i) - proboy_atr * a: continue
            if side == "long" and not b[i][4] > L(i) + proboy_atr * a: continue
            if obem_x > 0 and not b[i][5] > obem_x * st.mean(x[5] for x in b[i - 20:i]): continue
            kas = None
            for k in range(i + 1, min(len(b) - 5, i + 25)):
                if k - i < min_do_retesta:
                    if (side == "short" and b[k][4] > L(k) + 0.5 * a) or (side == "long" and b[k][4] < L(k) - 0.5 * a): break
                    continue
                if side == "short":
                    if b[k][4] > L(k) + 0.5 * a: break
                    if b[k][2] >= L(k) - 0.1 * a: kas = k; break
                else:
                    if b[k][4] < L(k) - 0.5 * a: break
                    if b[k][3] <= L(k) + 0.1 * a: kas = k; break
            if kas is None: continue
            pod = None
            for j in range(kas, min(len(b) - 2, kas + 4)):
                if side == "short" and b[j][4] < L(j) and b[j][4] < b[j][1]: pod = j; break
                if side == "long" and b[j][4] > L(j) and b[j][4] > b[j][1]: pod = j; break
            if pod is None: continue
            e = b[pod + 1][1]
            if side == "short": stop = max(x[2] for x in b[kas:pod + 1]) + 0.1 * a; risk = stop - e; zahod = (max(x[2] for x in b[kas:pod + 1]) - L(kas)) / a
            else: stop = min(x[3] for x in b[kas:pod + 1]) - 0.1 * a; risk = e - stop; zahod = (L(kas) - min(x[3] for x in b[kas:pod + 1])) / a
            if risk <= 0: continue
            r, k_vyh = progon(b, pod + 1, side, stop, risk)
            out.append(dict(sym=s, side=side, ts=b[pod + 1][0], j=pod + 1, R=r - KOM * e / risk, do_retesta=kas - i, zahod_atr=round(zahod, 3),
                            atr_pct=a / e * 100, stop_atr=risk / a, kom_R=KOM * e / risk))
            zanyato[side] = k_vyh
    return out

def kontrol(b, ev, rng):
    rs = []
    for _ in range(5):
        j = rng.randrange(130, len(b) - 26); a = atr(b, j)
        if not (a == a and a > 0): continue
        e = b[j][1]; risk = ev["stop_atr"] * a
        stop = e + risk if ev["side"] == "short" else e - risk
        r, _ = progon(b, j, ev["side"], stop, risk); rs.append(r - KOM * e / risk)
    return st.mean(rs) if rs else None

def t_dni(x):
    po = collections.defaultdict(list)
    for d, v in x: po[d].append(v)
    m = [st.mean(v) for v in po.values()]
    return (st.mean(m) / (st.stdev(m) / math.sqrt(len(m))), len(m)) if len(m) > 2 and st.stdev(m) > 0 else (None, len(m))

def main(prereg="PREREG_RETEST_SLOPED_2026_10_27.md", sha=SHA, imya="retest_sloped", **par):
    if hashlib.sha256((HERE / "prereg" / prereg).read_bytes()).hexdigest() != sha: sys.exit("prereg изменён")
    rng = random.Random(20261027); ev = []; t0 = time.time()
    for n, p in enumerate(sorted(glob.glob(str(HERE / "data" / "h1_kesh_att1" / "*.json")))):
        b = bary(p)
        if len(b) < 200: continue
        e = sobytiya(Path(p).stem, b, **par)
        for x in e: x["ctrl"] = kontrol(b, x, rng)
        ev += e
        if n % 100 == 0: print(n, len(ev), round(time.time() - t0), "с", flush=True)
    def q(v, p): v = sorted(v); return round(v[int(p * (len(v) - 1))], 3) if v else None
    zam = {}
    for side in ("short", "long", "vse"):
        g = [x for x in ev if side == "vse" or x["side"] == side]
        if not g: continue
        atrp = st.median(x["atr_pct"] for x in g)
        zam[side] = dict(sobytiy=len(g), monet=len({x["sym"] for x in g}), do_retesta_med=q([x["do_retesta"] for x in g], .5),
                         do_retesta_p90=q([x["do_retesta"] for x in g], .9), zahod_atr_med=q([x["zahod_atr"] for x in g], .5),
                         atr_pct_med=round(atrp, 3), stop_atr_med=q([x["stop_atr"] for x in g], .5), stop_atr_p90=q([x["stop_atr"] for x in g], .9),
                         kom_R_pri_05ATR=round(KOM * 100 / (0.5 * atrp), 3), kom_R_pri_1ATR=round(KOM * 100 / atrp, 3), kom_R_fakt_med=q([x["kom_R"] for x in g], .5))
    print("ЗАМЕРЫ:", json.dumps(zam, ensure_ascii=False, indent=1))
    pnl = {}
    for side in ("short", "long", "vse"):
        g = [x for x in ev if (side == "vse" or x["side"] == side) and x["ctrl"] is not None]
        if not g: continue
        d = lambda x: time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))
        tr, nd = t_dni([(d(x), x["R"] - x["ctrl"]) for x in g])
        pnl[side] = dict(n=len(g), dney=nd, R=round(st.mean(x["R"] for x in g), 4), kontrol=round(st.mean(x["ctrl"] for x in g), 4),
                         R_minus_kontrol=round(st.mean(x["R"] - x["ctrl"] for x in g), 4), t_dni=round(tr, 2) if tr else None,
                         vyigr=round(sum(x["R"] > 0 for x in g) / len(g), 3))
    v = pnl.get("vse", {}); ok = v.get("n", 0) >= 30 and v.get("R", 0) > 0 and v.get("R_minus_kontrol", 0) > 0 and (v.get("t_dni") or 0) >= 2
    out = dict(zamery=zam, pnl=pnl, vyvod="PASS_V_TEN" if ok else "FAIL")
    print("PnL:", json.dumps(pnl, ensure_ascii=False, indent=1)); print("ВЕРДИКТ:", out["vyvod"])
    f = HERE / "results" / time.strftime(imya + "_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(out, sobytiya=ev), ensure_ascii=False)); print("файл", f)

if __name__ == "__main__":
    main()
