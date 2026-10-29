#!/usr/bin/env python3
"""alpaca_aktivnaya.py — prereg/PREREG_ALPACA_AKTIVNAYA_2026_10_29.md. Только чтение дневок.  python3 research_lab/alpaca_aktivnaya.py <папка дневок>"""
import collections, csv, datetime as dt, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
def zag(p):
    out = {}
    for r in csv.DictReader(open(p)):
        d = dt.datetime.utcfromtimestamp(int(float(r["ts"]))).date(); out[d] = (float(r["o"]), float(r["c"]))
    return out
def t_(x): return st.mean(x) / (st.stdev(x) / math.sqrt(len(x))) if len(x) > 2 and st.stdev(x) > 0 else None
def dd(eq):
    pk = m = 0
    for v in eq: pk = max(pk, v); m = max(m, (pk - v) / pk if pk else 0)
    return m
def main():
    sha = hashlib.sha256((HERE / "prereg/PREREG_ALPACA_AKTIVNAYA_2026_10_29.md").read_bytes()).hexdigest()
    D = Path(sys.argv[1]); spy = zag(D / "SPY_M5.csv"); dni = sorted(spy)
    r = {dni[i]: spy[dni[i]][1] / spy[dni[i - 1]][1] - 1 for i in range(1, len(dni))}
    po_mes = collections.defaultdict(list)
    for d in dni: po_mes[(d.year, d.month)].append(d)
    okno = set()
    for k, ds in po_mes.items():
        okno |= set(ds[-3:])                                   # дни −3,−2,−1 (держим с закрытия −4-го: доходности дней −3..−1)
        nxt = (k[0] + (k[1] == 12), k[1] % 12 + 1)
        if nxt in po_mes: okno |= set(po_mes[nxt][:3])         # дни +1..+3
    dd_ = sorted(r); v_ok = [r[d] for d in dd_ if d in okno]; v_vne = [r[d] for d in dd_ if d not in okno]
    def polov(a, b): return [st.mean([r[d] for d in dd_ if a <= d.year <= b and d in okno]) - st.mean([r[d] for d in dd_ if a <= d.year <= b and d not in okno])]
    raz = st.mean(v_ok) - st.mean(v_vne); se = math.sqrt(st.pvariance(v_ok) / len(v_ok) + st.pvariance(v_vne) / len(v_vne)); tA = raz / se
    eqA, eqB = [1.0], [1.0]; vhod = False
    for d in dd_:
        if d in okno: eqA.append(eqA[-1] * (1 + r[d] - (0.0002 if not vhod else 0))); vhod = True
        else:
            if vhod: eqA[-1] *= 1 - 0.0002
            vhod = False; eqA.append(eqA[-1])
        eqB.append(eqB[-1] * (1 + r[d]))
    let = len(dd_) / 252
    rng = random.Random(20261029); dlina = len(okno) / len(po_mes); sl = []
    for _ in range(200):
        ok2 = set()
        for k, ds in po_mes.items():
            s0 = rng.randrange(0, max(1, len(ds) - 3)); ok2 |= set(ds[s0:s0 + 6])
        sl.append(st.mean([r[d] for d in dd_ if d in ok2]) * 252)
    A = dict(dnevnaya_raznica_bps=round(raz * 1e4, 2), t=round(tA, 2), polovina_2015_2020_bps=round(polov(2015, 2020)[0] * 1e4, 2), polovina_2021_2026_bps=round(polov(2021, 2026)[0] * 1e4, 2),
             dney_v_okne_dolya=round(len(v_ok) / len(dd_), 3), ruka_godovyh_pct=round((eqA[-1] ** (1 / let) - 1) * 100, 2), ruka_prosadka_pct=round(dd(eqA) * 100, 1),
             spy_godovyh_pct=round((eqB[-1] ** (1 / let) - 1) * 100, 2), spy_prosadka_pct=round(dd(eqB) * 100, 1),
             godovaya_v_okne_pct=round(st.mean(v_ok) * 252 * 100, 1), sluchaynye_okna_godovaya_pct_med=round(st.median(sl) * 100, 1))
    A["vyvod"] = "PASS_V_TEN" if raz > 0 and tA >= 2.24 and A["polovina_2015_2020_bps"] > 0 and A["polovina_2021_2026_bps"] > 0 else "FAIL"
    # B
    akc = {p.stem.replace("_M5", ""): zag(p) for p in D.glob("*_M5.csv") if p.stem not in ("SPY_M5", "QQQ_M5")}
    pt = [d for d in dni if d.weekday() == 4]; ex = []
    for i in range(1, len(pt) - 1):
        d0, d1, dm = pt[i], pt[i + 1], pt[i - 1]
        g = [(a[d0][1] / a[dm][1] - 1, s) for s, a in akc.items() if d0 in a and d1 in a and dm in a]
        if len(g) < 30: continue
        vse = st.mean(akc[s][d1][1] / akc[s][d0][1] - 1 for _, s in g)
        hud = sorted(g)[:5]; port = st.mean(akc[s][d1][1] / akc[s][d0][1] - 1 for _, s in hud) - 0.002
        ex.append((d0, port - vse))
    x = [v for _, v in ex]; tB = t_(x)
    p1 = [v for d, v in ex if d.year <= 2020]; p2 = [v for d, v in ex if d.year >= 2021]
    B = dict(nedel=len(x), izbytok_bps_v_nedelyu=round(st.mean(x) * 1e4, 2), t=round(tB, 2) if tB else None, polovina1_bps=round(st.mean(p1) * 1e4, 2), polovina2_bps=round(st.mean(p2) * 1e4, 2),
             godovoy_izbytok_pct=round(st.mean(x) * 52 * 100, 1), dolya_nedel_plus=round(sum(v > 0 for v in x) / len(x), 3))
    B["vyvod"] = "PASS_V_TEN" if st.mean(x) > 0 and (tB or 0) >= 2.24 and B["polovina1_bps"] > 0 and B["polovina2_bps"] > 0 else "FAIL"
    out = dict(prereg_sha=sha, A_rubezh_mesyaca=A, B_nedelnyy_otkat=B); print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("alpaca_aktivnaya_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(out, ensure_ascii=False, indent=1))
if __name__ == "__main__":
    main()
