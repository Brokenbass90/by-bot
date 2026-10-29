#!/usr/bin/env python3
"""fanding_mezhbirzhevoy.py — prereg/PREREG_FANDING_MEZHBIRZHEVOY_HVOST_2026_10_29.md. Mac (сеть Bybit + Binance), ~30–60 мин, кэш data/fmb_kesh.
    .venv/bin/python3 research_lab/fanding_mezhbirzhevoy.py > research_lab/data/fmb.log 2>&1"""
import collections, hashlib, json, math, statistics as st, sys, time, urllib.parse, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; SHA = "e9b5cbd1d663be3e0d63ca0df1ad3785788e6ed71ec7c025b3305af7c904a6bb"; OT, DO = 1735689600000, 1759276800000; W = 8 * 3600000; H4 = 4 * 3600000
KESH = HERE / "data" / "fmb_kesh"; KESH.mkdir(parents=True, exist_ok=True)
MEJ = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT"}

def get(u):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r: return json.loads(r.read())
        except Exception: time.sleep(1 + k)
    return None

def kesh(n, fn):
    f = KESH / (n + ".json")
    if f.exists(): return json.loads(f.read_text())
    v = fn(); f.write_text(json.dumps(v)); return v

def f_bybit(s):
    out, e = [], DO
    for _ in range(40):
        r = (get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={s}&startTime={OT - W}&endTime={e}&limit=200") or {}).get("result", {}).get("list") or []
        p = sorted((int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in r)
        if not p: break
        out = p + out; e = p[0][0] - 1
        if p[0][0] <= OT: break
        time.sleep(0.08)
    return sorted(set(out))

def f_binance(s):
    out, t = [], OT - W
    for _ in range(40):
        r = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={s}&startTime={t}&endTime={DO}&limit=1000") or []
        p = [(int(x["fundingTime"]), float(x["fundingRate"])) for x in r]
        if not p: break
        out += p; t = p[-1][0] + 1
        if len(p) < 1000: break
        time.sleep(0.1)
    return sorted(set(out))

def k_bybit(s):
    out, t = [], OT - W
    while t < DO:
        r = (get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={s}&interval=240&start={t}&end={min(DO, t + 999 * H4)}&limit=1000") or {}).get("result", {}).get("list") or []
        p = sorted((int(x[0]), float(x[4])) for x in r)
        if not p: break
        out += [q for q in p if not out or q[0] > out[-1][0]]; t = p[-1][0] + H4; time.sleep(0.08)
    return out

def k_binance(s):
    out, t = [], OT - W
    while t < DO:
        r = get(f"https://fapi.binance.com/fapi/v1/klines?symbol={s}&interval=4h&startTime={t}&limit=1500") or []
        p = [(int(x[0]), float(x[4])) for x in r]
        if not p: break
        out += [q for q in p if not out or q[0] > out[-1][0]]; t = p[-1][0] + H4
        if len(p) < 1500: break
        time.sleep(0.1)
    return out

def okna(f):
    o = collections.defaultdict(float)
    for t, r in f: o[(t - 1) // W * W] += r                      # выплата в момент t относится к окну, которое закончилось в t
    return o

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_FANDING_MEZHBIRZHEVOY_HVOST_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    by = {x["symbol"]: float(x.get("turnover24h") or 0) for x in (get("https://api.bybit.com/v5/market/tickers?category=linear") or {}).get("result", {}).get("list", [])}
    bn = {x["symbol"] for x in (get("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}).get("symbols", []) if x.get("contractType") == "PERPETUAL"}
    syms = [s for s, _ in sorted(by.items(), key=lambda kv: -kv[1]) if s.endswith("USDT") and s in bn and s not in MEJ][:150]
    print("монет:", len(syms), flush=True); sd = []
    for n, s in enumerate(syms, 1):
        fa, fb = okna(kesh(f"fby_{s}", lambda: f_bybit(s))), okna(kesh(f"fbn_{s}", lambda: f_binance(s)))
        pa, pb = dict(map(tuple, kesh(f"kby_{s}", lambda: k_bybit(s)))), dict(map(tuple, kesh(f"kbn_{s}", lambda: k_binance(s))))
        ks = sorted(set(fa) & set(fb)); k = 1
        while k < len(ks):
            w0, w1 = ks[k - 1], ks[k]
            if not (OT <= w1 < DO) or w1 - w0 != W: k += 1; continue
            raz = fa[w0] - fb[w0]
            if abs(raz) < 5e-4 or w1 not in pa or w1 not in pb: k += 1; continue
            side = 1 if raz > 0 else -1                                 # +1: шорт Bybit / лонг Binance
            fund, j = 0.0, k
            while j < len(ks) and j < k + 3:
                w = ks[j]; r = fa.get(w, 0) - fb.get(w, 0); fund += side * r
                j += 1
                if r * side < 0: break
            vyh = ks[j - 1] + W
            if vyh not in pa or vyh not in pb: k = j; continue
            bazis = side * ((pb[vyh] / pb[w1] - 1) - (pa[vyh] / pa[w1] - 1))      # лонг на Binance, шорт на Bybit при side=+1
            net = (fund + bazis) * 1e4 - 25
            sd.append(dict(sym=s, ts=w1, okon=j - k, fund_bps=round(fund * 1e4, 2), bazis_bps=round(bazis * 1e4, 2), net_bps=round(net, 2))); k = j
        if n % 25 == 0: print(n, len(syms), len(sd), flush=True)
    if not sd: sys.exit("нет сделок")
    x = [z["net_bps"] for z in sd]; po = collections.defaultdict(list); mes = collections.defaultdict(float)
    for z in sd: d = time.strftime("%Y-%m-%d", time.gmtime(z["ts"] / 1000)); po[d].append(z["net_bps"]); mes[d[:7]] += z["net_bps"] / 1e4 * 1000
    m = [st.mean(v) for v in po.values()]; t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
    bez5 = sum(sorted(x)[:-5])
    out = dict(sdelok=len(sd), monet=len({z["sym"] for z in sd}), sred_net_bps=round(st.mean(x), 2), med=round(st.median(x), 2), t_dni=round(t, 2) if t else None,
               fanding_sred=round(st.mean(z["fund_bps"] for z in sd), 2), bazis_sred=round(st.mean(z["bazis_bps"] for z in sd), 2), okon_sred=round(st.mean(z["okon"] for z in sd), 2),
               mesyacy_usd_na_1000={k: round(v, 1) for k, v in sorted(mes.items())}, mesyacev_plus=sum(v > 0 for v in mes.values()), bez5_bps_summa=round(bez5, 1))
    out["vyvod"] = "PASS_V_TEN" if len(sd) >= 200 and out["sred_net_bps"] > 0 and (t or 0) >= 2 and out["mesyacev_plus"] >= 6 and bez5 > 0 else "FAIL"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("fanding_mezhbirzhevoy_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(out, sdelki=sd), ensure_ascii=False))

if __name__ == "__main__":
    main()
