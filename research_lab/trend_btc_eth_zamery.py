import json, math, statistics as st, sys, datetime as dt
from pathlib import Path
D = Path(sys.argv[1])
def weekly(sym):
    rows = json.load(open(D / f"{sym}.json"))
    w = {}
    for ts, o, h, l, c, v in rows:
        d = dt.datetime.utcfromtimestamp(ts / 1000).date()
        if d > dt.date(2021, 4, 30): continue
        k = d.isocalendar()[:2]
        w[k] = c  # последняя цена недели
    ks = sorted(w); px = [w[k] for k in ks]
    return [math.log(px[i] / px[i - 1]) for i in range(1, len(px))][1:-1]  # без неполных крайних недель
def welch(a, b):
    ma, mb = st.mean(a), st.mean(b); se = math.sqrt(st.variance(a) / len(a) + st.variance(b) / len(b))
    return ma - mb, (ma - mb) / se
out = {}
R = {s: weekly(s) for s in ("BTCUSDT", "ETHUSDT")}
for L in (4, 12, 26):
    res = {}
    pool_up, pool_dn = [], []
    for s, r in R.items():
        up, dn = [], []
        for i in range(L, len(r)):
            past = sum(r[i - L:i]); (up if past > 0 else dn).append(r[i])
        d, t = welch(up, dn); res[s] = {"raznica_%": round(d * 100, 2), "t": round(t, 2), "n_up": len(up), "n_dn": len(dn)}
        pool_up += up; pool_dn += dn
    d, t = welch(pool_up, pool_dn); res["vmeste"] = {"raznica_%": round(d * 100, 2), "t": round(t, 2)}
    out[f"L{L}"] = res
hit = []
for s, r in R.items():
    for i in range(12, len(r)):
        hit.append((sum(r[i - 12:i]) > 0) == (r[i] > 0))
out["sovpadenie_znaka_L12"] = round(sum(hit) / len(hit), 3)
vr = {}
for s, r in R.items():
    r4 = [sum(r[i:i + 4]) for i in range(0, len(r) - 3)]
    vr[s] = round(st.variance(r4) / (4 * st.variance(r)), 3)
allr = R["BTCUSDT"] + R["ETHUSDT"]
out["VR4"] = vr
out["nedel"] = {s: len(r) for s, r in R.items()}
L = out
ok = sum(L[f"L{x}"]["vmeste"]["raznica_%"] > 0 for x in (4, 12, 26)) >= 2 and L["L12"]["vmeste"]["t"] >= 1.0 and all(v > 1 for v in vr.values())
out["reshenie"] = "K_PNL_TESTU" if ok else "MEHANIZM_NE_PODTVERZHDEN"
print(json.dumps(out, ensure_ascii=False, indent=1))
