import datetime as dt, json, sys, hashlib
sys.path.insert(0, "."); sys.path.insert(0, "factory_v3")
import numpy as np
import discovery_paket1 as P, kity_sudya as K
from reestr_v1 import Reestr
OKNO = "KRIPTO_D1_2021H2_2022"; A, B_ = dt.date(2021, 7, 1), dt.date(2022, 12, 31)
M = K.zagruzit()
def ts(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
def nedelya(d, lookback):
    vch = (d - dt.timedelta(days=1)).isoformat()
    oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
    rows = []
    for _, s in oi:
        x = M[s]; i = int(np.searchsorted(x["ts"], ts(d)))
        if i >= len(x["ts"]) or x["ts"][i] != ts(d) or i < 60: continue
        j1 = i - 1; j0 = int(np.searchsorted(x["ts"], ts(d) - (lookback + 1) * P.DEN))
        if x["ts"][j0] != ts(d) - (lookback + 1) * P.DEN: continue
        rows.append((x["c"][j1] / x["c"][j0] - 1, s, i))
    if len(rows) < 30: return None
    rows.sort(); k = len(rows) // 10
    leg = [K.sdelka(M[s], i, 7, -1) for _, s, i in rows[:k]] + [K.sdelka(M[s], i, 7, +1) for _, s, i in rows[-k:]]
    leg = [r for r in leg if r is not None]
    return float(np.mean(leg)) if leg else None
R = Reestr(); out = {}
for gid, lb, sem in (("MOM30_XS", 30, "MOMENTUM_30D"), ("IMP7_XS", 7, "IMPULS_7D")):
    spec = dict(gipoteza=gid, lookback_dney=lb, decil=0.1, hold=7, vselennaya="PIT top50 OI Binance", okno=OKNO, prereg="PREREG_KRIPTO_MOMENTUM_XS_2026_10_20")
    S = R.sostoyanie()
    if gid not in S["gipotezy"]:
        R.gipoteza(gid, sem, f"кросс-секционный моментум {lb} дн., лонг верхний/шорт нижний дециль, 7 дн.", ["binance_klines_d1", "binance_metrics_oi"],
                   otlichie="классический XS-моментум по доходности; не поток тейкеров, не толпа, не тренд мажоров")
    pid = f"{gid}__SCREEN"
    R.zaregistrirovat_popytku(pid, gid, OKNO, "SCREEN", spec, {"min_n": 30, "znak": "+"})
    sob = [(ts(d), r, None) for d in K.SETKA if A <= d <= B_ for r in [nedelya(d, lb)] if r is not None]
    it = P.itog(sob, s_kontrolem=False, lag=1)
    rez = R.zapisat_rezultat(pid, spec, it.get("t", 0.0), it.get("n", 0), metrika=it)
    out[gid] = dict(itog=it, verdikt_reestra=rez.get("verdikt") if isinstance(rez, dict) else str(rez))
    print(gid, json.dumps(out[gid], ensure_ascii=False))
json.dump(out, open("results/kripto_momentum_xs_20261020.json", "w"), ensure_ascii=False, indent=1, default=str)
