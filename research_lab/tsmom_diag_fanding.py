"""Диагностика (описание, не вердикт): A2 с реальным фандингом Binance для шортов вместо консервативного 1 bp/8ч."""
import datetime as dt, json, math, statistics as st, sys
import tsmom_btc_eth as T
T.END = dt.date(2022, 12, 31); T.D = T.Path("data/binance_kity/klines")
START = dt.date(2021, 7, 1); L = 12
def fund_week(sym, dates):
    f = json.load(open(f"data/binance/funding/{sym}.json")); s = {}
    for ts, r in f:
        d = dt.datetime.utcfromtimestamp(ts / 1000).date(); s[d.isocalendar()[:2]] = s.get(d.isocalendar()[:2], 0) + r
    # доходность r[i] — неделя, заканчивающаяся dates[i] (dates уже сдвинуты на 1)
    return [s.get(d.isocalendar()[:2]) for d in dates]
def leg_real(r, fw):
    out, prev = [], 0.0
    for i in range(L, len(r)):
        sg = 1 if sum(r[i-L:i]) > 0 else -1
        sig = st.pstdev(r[i-12:i]) * math.sqrt(52); w = sg * min(T.CAP, T.TV / sig)
        ret = w * (math.exp(r[i]) - 1) - abs(w - prev) * T.COST
        if w < 0 and fw[i] is not None: ret += abs(w) * fw[i]   # шорт получает положительный фандинг
        prev = w; out.append(ret)
    return out
out = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    d, r = T.weekly(sym); fw = fund_week(sym, d)
    keep = [i for i, x in enumerate(d[L:]) if x >= START]
    out[sym] = {"konservativno": T.stats([T.leg(r, L)[i] for i in keep]), "realnyy_fanding": T.stats([leg_real(r, fw)[i] for i in keep]),
                "nedel_short": sum(1 for i in keep if sum(r[i:i+L]) <= 0), "sredniy_fanding_nedelya_%": round(st.mean(x for x in fw if x is not None) * 100, 3)}
print(json.dumps(out, ensure_ascii=False, indent=1))
