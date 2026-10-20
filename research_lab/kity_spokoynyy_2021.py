import datetime as dt, json, math, statistics as st, sys
sys.path.insert(0, ".")
import numpy as np
import discovery_paket1 as P, kity_sudya as K
POROG = 0.427
M = K.zagruzit()
for s, x in M.items():
    f = K.B / "taker" / f"{s}.json"; tk = {}
    if f.exists():
        for t, qv, tq in json.loads(f.read_text()):
            if qv > 0: tk[K.den(t).isoformat()] = tq / qv
    x["taker"] = tk
def ts(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
def nedelya(d):
    vch = (d - dt.timedelta(days=1)).isoformat()
    oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
    rows = []
    for _, s in oi:
        x = M[s]; i = int(np.searchsorted(x["ts"], ts(d)))
        if i >= len(x["ts"]) or x["ts"][i] != ts(d) or i < 60: continue
        v = x["taker"].get(vch)
        if v is not None and np.isfinite(v): rows.append((v, s, i))
    if len(rows) < 30: return None
    rows.sort(); k = len(rows) // 10
    leg = [K.sdelka(M[s], i, 7, -1) for _, s, i in rows[:k]] + [K.sdelka(M[s], i, 7, +1) for _, s, i in rows[-k:]]
    leg = [r for r in leg if r is not None]
    return float(np.mean(leg)) if leg else None
bt = json.load(open(K.B / "klines" / "BTCUSDT.json")); bc = {dt.datetime.utcfromtimestamp(r[0] / 1000).date(): r[4] for r in bt}
def vol(d):
    dd = [bc[d - dt.timedelta(i)] / bc[d - dt.timedelta(i + 1)] - 1 for i in range(1, 29) if d - dt.timedelta(i) in bc and d - dt.timedelta(i + 1) in bc]
    return st.stdev(dd) * math.sqrt(365) if len(dd) >= 20 else None
rows = []
for d in K.SETKA:
    if not (K.REPLIK[0] <= d <= K.REPLIK[1]): continue
    r = nedelya(d); v = vol(d)
    if r is None or v is None: continue
    rows.append(dict(d=d.isoformat(), bps=r * 1e4, vol=v, rezhim="NIZKAYA" if v < POROG else "VYSOKAYA"))
def sv(g):
    x = [r["bps"] for r in g]
    if len(x) < 3: return dict(n=len(x))
    sob = [(ts(dt.date.fromisoformat(r["d"])), r["bps"] / 1e4, None) for r in g]
    it = P.itog(sob, s_kontrolem=False, lag=1) if len(sob) >= 20 else {}
    return dict(n=len(x), sred_bps=round(st.mean(x), 1), t_prostoy=round(st.mean(x) / (st.stdev(x) / math.sqrt(len(x))), 2), t_sudyi=it.get("t"))
nz = [r for r in rows if r["rezhim"] == "NIZKAYA"]; vy = [r for r in rows if r["rezhim"] == "VYSOKAYA"]
out = dict(nedel=len(rows), vse=sv(rows), spokoynye=sv(nz), burnye=sv(vy))
s = out["spokoynye"]; t = s.get("t_sudyi") if s.get("t_sudyi") is not None else s.get("t_prostoy")
out["verdikt"] = ("BLOCKED_DATA" if s["n"] < 20 else ("PASS" if s.get("sred_bps", -1) > 0 and t is not None and t >= 2.0 and s["sred_bps"] > out["burnye"].get("sred_bps", 1e9) else "FAIL"))
out["nedeli"] = rows
json.dump(out, open("results/kity_spokoynyy_2021_2022_20261020.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "nedeli"}, ensure_ascii=False))
