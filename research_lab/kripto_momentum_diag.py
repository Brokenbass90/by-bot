"""Диагностика MOM30_XS (−76.7 bps/нед, 2021H2–2022) по PM 20.10: ноги отдельно, gross/net, фандинг, PIT, BTC, недели, ДИ и MDE.
Без новых параметров; спецификация та же, что у попытки MOM30_XS__SCREEN."""
import datetime as dt, json, math, statistics as st, sys
sys.path.insert(0, ".")
import numpy as np
import discovery_paket1 as P, kity_sudya as K
A, B_ = dt.date(2021, 7, 1), dt.date(2022, 12, 31)
M = K.zagruzit()
def ts(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
def noga(x, i, side):
    t_vyh = int(x["ts"][i]) + 7 * P.DEN; j = int(np.searchsorted(x["ts"], t_vyh, side="right")) - 1
    if j <= i: return None
    g = side * (x["c"][j] / x["c"][i] - 1); f = side * P.fand(x, x["ts"][i], x["ts"][j])
    return g, f, P.KOM_KRIPTO
rows = []; pit_ok = 0; pit_vse = 0
bt = M["BTCUSDT"]
for d in K.SETKA:
    if not (A <= d <= B_): continue
    vch = (d - dt.timedelta(days=1)).isoformat()
    oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
    cand = []
    for _, s in oi:
        x = M[s]; i = int(np.searchsorted(x["ts"], ts(d)))
        if i >= len(x["ts"]) or x["ts"][i] != ts(d) or i < 60: continue
        j0 = int(np.searchsorted(x["ts"], ts(d) - 31 * P.DEN))
        if x["ts"][j0] != ts(d) - 31 * P.DEN: continue
        pit_vse += 1; pit_ok += int(x["ts"][i - 1] < ts(d))            # признак только из закрытых до d баров
        cand.append((x["c"][i - 1] / x["c"][j0] - 1, s, i))
    if len(cand) < 30: continue
    cand.sort(); k = len(cand) // 10
    L = [noga(M[s], i, +1) for _, s, i in cand[-k:]]; S = [noga(M[s], i, -1) for _, s, i in cand[:k]]
    L = [z for z in L if z]; S = [z for z in S if z]
    if not L or not S: continue
    ib = int(np.searchsorted(bt["ts"], ts(d))); jb = int(np.searchsorted(bt["ts"], ts(d) + 7 * P.DEN, side="right")) - 1
    rows.append(dict(d=d.isoformat(), long_g=np.mean([z[0] for z in L]), short_g=np.mean([z[0] for z in S]),
                     fand=np.mean([z[1] for z in L + S]), kom=P.KOM_KRIPTO,
                     net=np.mean([z[0] - z[1] - z[2] for z in L + S]), btc=bt["c"][jb] / bt["c"][ib] - 1,
                     top=[s for _, s, _ in cand[-k:]], niz=[s for _, s, _ in cand[:k]]))
def sv(v): 
    v = [x * 1e4 for x in v]; m = st.mean(v); se = st.stdev(v) / math.sqrt(len(v)); return dict(sred_bps=round(m, 1), t=round(m / se, 2), di95=(round(m - 1.96 * se, 1), round(m + 1.96 * se, 1)))
out = dict(nedel=len(rows), pit_priznak_iz_zakrytyh=f"{pit_ok}/{pit_vse}",
           net=sv([r["net"] for r in rows]), long_noga_gross=sv([r["long_g"] for r in rows]), short_noga_gross=sv([r["short_g"] for r in rows]),
           fanding_sred_bps=round(st.mean(r["fand"] for r in rows) * 1e4, 1), komissiya_bps=round(P.KOM_KRIPTO * 1e4, 1))
nets = sorted(r["net"] * 1e4 for r in rows); bez = [x for x in sorted(r["net"] * 1e4 for r in rows)][2:-2]
out["bez_2_hudshih_i_2_luchshih"] = round(st.mean(bez), 1)
out["korr_net_btc"] = round(float(np.corrcoef([r["net"] for r in rows], [r["btc"] for r in rows])[0, 1]), 2)
up = [r["net"] * 1e4 for r in rows if r["btc"] > 0]; dn = [r["net"] * 1e4 for r in rows if r["btc"] <= 0]
out["btc_nedelya_vverh"] = (len(up), round(st.mean(up), 1)); out["btc_nedelya_vniz"] = (len(dn), round(st.mean(dn), 1))
from collections import Counter
cnt = Counter(s for r in rows for s in r["top"] + r["niz"]); out["chashche_vsego_v_nogah"] = cnt.most_common(6)
sd = st.stdev(r["net"] * 1e4 for r in rows); out["MDE_bps_pri_t2"] = round(2 * sd / math.sqrt(len(rows)), 1)
out["nedel_dlya_MDE_20bps"] = math.ceil((2 * sd / 20) ** 2)
json.dump(out, open("results/kripto_momentum_diag_20261020.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str))
