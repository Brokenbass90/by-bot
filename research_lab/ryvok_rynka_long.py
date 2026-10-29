#!/usr/bin/env python3
"""ryvok_rynka_long.py — prereg/PREREG_RYVOK_RYNKA_LONG_2026_10_29.md. Только чтение кэшей.  python3 research_lab/ryvok_rynka_long.py"""
import collections, glob, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; H = 3600000; KOM = 0.002
SHA = "86b77243e9602e193d0f13aa5e78385616822d79732325885ec8c76aed04dfca"

def atr(b, j):
    tr = [max(b[k][2] - b[k][3], abs(b[k][2] - b[k - 1][4]), abs(b[k][3] - b[k - 1][4])) for k in range(j - 14, j) if k - 1 >= 0]
    return sum(tr) / len(tr) if tr else None

def lng(b, j, a):
    e = b[j][1]; stop, tg = e - 2 * a, e + 6 * a
    for k in range(j, min(len(b), j + 48)):
        if b[k][3] <= stop: return -1.0 - KOM * e / (2 * a)
        if b[k][2] >= tg: return 3.0 - KOM * e / (2 * a)
    k = min(len(b), j + 48) - 1; return (b[k][4] - e) / (2 * a) - KOM * e / (2 * a)

def t_dni(pairs):
    po = collections.defaultdict(list)
    for d, v in pairs: po[d].append(v)
    m = [st.mean(v) for v in po.values()]
    return (round(st.mean(m) / (st.stdev(m) / math.sqrt(len(m))), 2) if len(m) > 2 and st.stdev(m) > 0 else None), len(m)

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_RYVOK_RYNKA_LONG_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    rng = random.Random(20261029); A = []
    # 2025
    S25 = sorted([x for x in json.load(open(sorted(glob.glob(str(HERE / "results" / "pump4_filtr_istoriya_*.json")))[-1]))["sdelki"]], key=lambda x: x["ts"])
    B25 = {}
    for x in S25:
        if sum(1 for y in S25 if x["ts"] - 24 * H <= y["ts"] < x["ts"]) < 5: continue
        if x["sym"] not in B25:
            f = HERE / "data" / "flet_2025_kesh" / f'{x["sym"]}.json'; B25[x["sym"]] = json.load(open(f)) if f.exists() else []
        b = B25[x["sym"]]; idx = {r[0]: i for i, r in enumerate(b)}; j = idx.get(x["ts"] + H)
        if j is None or j < 20 or j + 48 >= len(b): continue
        a = atr(b, j); r = lng(b, j, a)
        cs = [lng(b, k, atr(b, k)) for k in (rng.randrange(20, len(b) - 49) for _ in range(5)) if atr(b, k)]
        A.append(dict(god=2025, sym=x["sym"], ts=x["ts"], R=r, ctrl=st.mean(cs), pump4_R=x["R"]))
    # 2026
    S26 = sorted([x for x in json.load(open(sorted(glob.glob(str(HERE / "results" / "pump4_polnyy_povtor_*.json")))[-1]))["sdelki"] if x.get("R") is not None], key=lambda x: x["ts"])
    for x in S26:
        if sum(1 for y in S26 if x["ts"] - 24 * H <= y["ts"] < x["ts"]) < 5: continue
        f = HERE / "data" / "razbor_dannye" / f'PUMP4_{x["sym"]}_{x["ts"] + H}.json'
        if not f.exists(): continue
        b = sorted(json.load(open(f))["perp"]); idx = {r[0]: i for i, r in enumerate(b)}; j = idx.get(x["ts"] + H)
        if j is None or j < 20 or j + 48 >= len(b): continue
        a = atr(b, j); r = lng(b, j, a)
        cs = [lng(b, k, atr(b, k)) for k in (rng.randrange(20, len(b) - 49) for _ in range(5)) if atr(b, k)]
        A.append(dict(god=2026, sym=x["sym"], ts=x["ts"], R=r, ctrl=st.mean(cs), pump4_R=x["R"]))
    d = lambda x: time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))
    tA, nd = t_dni([(d(x), x["R"] - x["ctrl"]) for x in A]) if A else (None, 0)
    pl = [x["R"] for x in A if x["pump4_R"] < 0]
    oA = dict(n=len(A), po_godam=dict(collections.Counter(x["god"] for x in A)), R=round(st.mean(x["R"] for x in A), 3) if A else None,
              kontrol=round(st.mean(x["ctrl"] for x in A), 3) if A else None, vklad=round(st.mean(x["R"] - x["ctrl"] for x in A), 3) if A else None, t_dni=tA, dney=nd,
              R_kogda_PUMP4_minus=round(st.mean(pl), 3) if pl else None, n_PUMP4_minus=len(pl))
    oA["vyvod"] = "PASS_V_TEN" if oA["n"] >= 30 and (oA["R"] or 0) > 0 and (oA["vklad"] or 0) > 0 and (tA or 0) >= 2.24 and (oA["R_kogda_PUMP4_minus"] or 0) > 0 else "FAIL"
    # B — корзина 2025
    B = {}
    for f in glob.glob(str(HERE / "data" / "flet_2025_kesh" / "*.json")):
        b = json.load(open(f))
        if len(b) > 1000: B[Path(f).stem] = {r[0]: r for r in b}
    vse_t = sorted(set().union(*[set(v) for v in B.values()])); OT, DO = 1735689600000, 1759276800000
    def rost(s, t): b = B[s]; return (b[t][4] / b[t - 24 * H][4] - 1) if t in b and t - 24 * H in b else None
    def korz(t):
        rs = sorted([(rost(s, t), s) for s in B if rost(s, t) is not None and t + 24 * H in B[s]], reverse=True)[:5]
        if len(rs) < 5: return None
        return st.mean(max(-0.2, B[s][t + 24 * H][4] / B[s][t + H][1] - 1) - KOM for _, s in rs if t + H in B[s]) * 100
    ryv, posl = [], -10**15; ne_ryv = []
    for t in vse_t:
        if not (OT <= t < DO): continue
        rr = [rost(s, t) for s in B]; rr = [x for x in rr if x is not None]
        if len(rr) < 50: continue
        dolya = sum(x >= 0.05 for x in rr) / len(rr)
        if dolya >= 0.20:
            if t - posl > 24 * H: ryv.append(t)
            posl = t
        elif t % (6 * H) == 0: ne_ryv.append(t)
    Bres = []
    for t in ryv:
        k = korz(t)
        if k is None: continue
        cs = [c for c in (korz(rng.choice(ne_ryv)) for _ in range(5)) if c is not None]
        Bres.append(dict(ts=t, pct=k, ctrl=st.mean(cs) if cs else 0))
    tB, ndB = t_dni([(d(x), x["pct"] - x["ctrl"]) for x in Bres]) if Bres else (None, 0)
    oB = dict(n=len(Bres), sred_pct=round(st.mean(x["pct"] for x in Bres), 3) if Bres else None, kontrol=round(st.mean(x["ctrl"] for x in Bres), 3) if Bres else None,
              t_dni=tB, sobytiya=[(d(x), round(x["pct"], 2)) for x in Bres])
    oB["vyvod"] = "PASS_V_TEN" if oB["n"] >= 30 and (oB["sred_pct"] or 0) > 0 and (oB["sred_pct"] or 0) > (oB["kontrol"] or 0) and (tB or 0) >= 2.24 else "FAIL"
    out = dict(A=oA, B=oB); print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("ryvok_rynka_long_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(out, sdelki_A=A), ensure_ascii=False))

if __name__ == "__main__":
    main()
