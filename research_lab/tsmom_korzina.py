"""TSMOM_KORZINA — prereg research_lab/prereg/PREREG_TSMOM_KORZINA_D1_2026_10_22.md
Запуск: python3 tsmom_korzina.py <папка дневок> <начало YYYY-MM-DD> <конец YYYY-MM-DD> <выход.json>"""
import datetime as dt, json, math, random, statistics as st, sys
from pathlib import Path
SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT", "TRXUSDT", "EOSUSDT", "XLMUSDT", "LINKUSDT"]
COST, FUND, TV, CAP, L = 8e-4, 1e-4 * 21, 0.20, 1.5, 12
D, START, END, OUT = Path(sys.argv[1]), dt.date.fromisoformat(sys.argv[2]), dt.date.fromisoformat(sys.argv[3]), sys.argv[4]

def weekly(sym):
    p = D / f"{sym}.json"
    if not p.exists(): return {}
    w = {}
    for ts, o, h, l, c, v in json.load(open(p)):
        d = dt.datetime.utcfromtimestamp(ts / 1000).date()
        if d <= END: w[d.isocalendar()[:2]] = (d, c)
    ks = sorted(w)[1:-1]
    return {ks[i]: (w[ks[i]][0], math.log(w[ks[i]][1] / w[ks[i - 1]][1])) for i in range(1, len(ks))}

def leg(wk, signs=None, mode="ls"):
    ks = sorted(wk); r = [wk[k][1] for k in ks]; out, prev = {}, 0.0
    for i in range(L, len(r)):
        sg = (1 if sum(r[i - L:i]) > 0 else -1) if signs is None else signs.get(ks[i], 1)
        if mode == "long" and sg < 0: sg = 0
        if mode == "hold": sg = 1
        sig = st.pstdev(r[i - 12:i]) * math.sqrt(52); w = sg * min(CAP, TV / sig) if sig > 0 else 0.0
        ret = w * (math.exp(r[i]) - 1) - abs(w - prev) * COST - (abs(w) * FUND if w < 0 else 0.0)
        prev = w
        if wk[ks[i]][0] >= START: out[ks[i]] = ret
    return out

def port(legs):
    keys = sorted(set().union(*[set(x) for x in legs]))
    return keys, [st.mean([x[k] for x in legs if k in x]) for k in keys]

def stats(p):
    n = len(p); m, s = st.mean(p), st.pstdev(p); eq, pk, mdd = 1.0, 1.0, 0.0
    for x in p: eq *= 1 + x; pk = max(pk, eq); mdd = max(mdd, 1 - eq / pk)
    return {"n_nedel": n, "t": round(m / (s / math.sqrt(n)), 2), "god_%": round((eq ** (52.18 / n) - 1) * 100, 1),
            "sharpe": round(m / s * math.sqrt(52), 2), "maks_prosadka_%": round(mdd * 100, 1)}

W = {s: weekly(s) for s in SYMS}; W = {s: w for s, w in W.items() if len(w) > L + 4}
legs = {s: leg(w) for s, w in W.items()}
keys, P = port(list(legs.values()))
out = {"monety": list(W), "osnovnaya": stats(P), "po_monetam_god_%": {s: stats(list(x.values()))["god_%"] for s, x in legs.items() if len(x) > 10}}
rng = random.Random(20261022); real = st.mean(P); better = 0
for _ in range(2000):
    q = [leg(w, signs={k: rng.choice((1, -1)) for k in w}) for w in W.values()]
    if st.mean(port(q)[1]) >= real: better += 1
out["p_perestanovok"] = round(better / 2000, 4)
out["kupit_derzhat_tot_zhe_risk"] = stats(port([leg(w, mode="hold") for w in W.values()])[1])
out["tolko_long"] = stats(port([leg(w, mode="long") for w in W.values()])[1])
out["prevyshenie_nad_derzhat_god_%"] = round(out["osnovnaya"]["god_%"] - out["kupit_derzhat_tot_zhe_risk"]["god_%"], 1)
pm = sum(1 for v in out["po_monetam_god_%"].values() if v > 0); out["monet_v_plyuse"] = f"{pm}/{len(out['po_monetam_god_%'])}"
yrs = {}
d0 = {k: v[0] for w in W.values() for k, v in w.items()}
for k, x in zip(keys, P): yrs.setdefault(d0[k].year, []).append(x)
out["po_godam_%"] = {y: round((math.prod(1 + x for x in v) - 1) * 100, 1) for y, v in yrs.items()}
print(json.dumps(out, ensure_ascii=False, indent=1)); json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
