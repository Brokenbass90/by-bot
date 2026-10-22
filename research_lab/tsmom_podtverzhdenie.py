"""Подтверждение TSMOM_BTC_ETH_V1 на окне KRIPTO_D1_2021H2_2022 тем же правилом (prereg cf6d9bf, одна попытка)."""
import datetime as dt, json, random, statistics as st, sys
import tsmom_btc_eth as T
T.END = dt.date(2022, 12, 31)
T.D = T.Path("data/binance_kity/klines")
START = dt.date(2021, 7, 1)
L = 12
dB, rB = T.weekly("BTCUSDT"); dE, rE = T.weekly("ETHUSDT"); assert dB == dE
dates = dB[L:]
keep = [i for i, d in enumerate(dates) if d >= START]
cut = lambda xs: [xs[i] for i in keep]
a, b = cut(T.leg(rB, L)), cut(T.leg(rE, L))
P = T.port(a, b)
out = {"osnovnaya_L12": T.stats(P), "BTC": T.stats(a), "ETH": T.stats(b)}
rng = random.Random(20261022); real = st.mean(P); better = 0
for _ in range(2000):
    sa = [rng.choice((1, -1)) for _ in range(len(rB) - L)]; sb = [rng.choice((1, -1)) for _ in range(len(rE) - L)]
    if st.mean(T.port(cut(T.leg(rB, L, signs=sa)), cut(T.leg(rE, L, signs=sb)))) >= real: better += 1
out["p_perestanovok"] = round(better / 2000, 4)
out["kupit_derzhat_tot_zhe_risk"] = T.stats(T.port(cut(T.leg(rB, L, signs=[1]*(len(rB)-L))), cut(T.leg(rE, L, signs=[1]*(len(rE)-L)))))
out["tolko_long_L12"] = T.stats(T.port(cut(T.leg(rB, L, long_only=True)), cut(T.leg(rE, L, long_only=True))))
po = {}
for i, x in zip(keep, P): po.setdefault(dates[i].year, []).append(x)
import math
out["po_godam_%"] = {y: round((math.prod(1 + x for x in v) - 1) * 100, 1) for y, v in po.items()}
out["period"] = [str(dates[keep[0]]), str(dates[keep[-1]])]
print(json.dumps(out, ensure_ascii=False, indent=1)); json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
