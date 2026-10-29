#!/usr/bin/env python3
"""short_hvost_istoriya_2025.py — prereg/PREREG_SHORT_HVOST_ISTORIYA_2025_2026_10_29.md. Mac (сеть Bybit), ~30–50 мин. Только чтение. Кэш: data/shvost_2025_kesh/.
    .venv/bin/python3 research_lab/short_hvost_istoriya_2025.py > research_lab/data/shvost_2025.log 2>&1"""
import bisect, collections, hashlib, json, math, statistics as st, sys, time, urllib.parse, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import fanding_hvost as F
SHA = "6176b324e149a8680b319468de16dd44d058a5ae93cd351d355517e035adcb12"; H, DEN = 3600000, 86400000; OT, DO = 1735689600000, 1759276800000
KESH = HERE / "data" / "shvost_2025_kesh"; KESH.mkdir(parents=True, exist_ok=True)
YAKORYA = {"ADAUSDT", "BTCUSDT", "DOTUSDT", "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "SUIUSDT"}

def get(path, **p):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request("https://api.bybit.com/v5/" + path + "?" + urllib.parse.urlencode(p), headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r:
                return json.loads(r.read()).get("result") or {}
        except Exception: time.sleep(1 + k)
    return {}

def kesh(imya, fn):
    f = KESH / (imya + ".json")
    if f.exists(): return json.loads(f.read_text())
    v = fn(); f.write_text(json.dumps(v)); return v

def kline(sym, interval, t0, t1, shag):
    out, s = [], t0
    while s < t1:
        l = get("market/kline", category="linear", symbol=sym, interval=interval, start=s, end=min(t1, s + 999 * shag), limit=1000).get("list") or []
        part = sorted([[int(x[0])] + [float(v) for v in x[1:7]] for x in l])
        if not part: break
        out += [q for q in part if not out or q[0] > out[-1][0]]; s = part[-1][0] + shag; time.sleep(0.08)
    return out

def fanding(sym, t0, t1):
    out, e = [], t1
    for _ in range(30):
        l = get("market/funding/history", category="linear", symbol=sym, startTime=t0, endTime=e, limit=200).get("list") or []
        r = sorted((int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in l)
        if not r: break
        out = r + out; e = r[0][0] - 1
        if r[0][0] <= t0: break
        time.sleep(0.08)
    return sorted(set(out))

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_SHORT_HVOST_ISTORIYA_2025_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    inst, cur = [], ""
    while True:
        r = get("market/instruments-info", category="linear", limit=1000, **({"cursor": cur} if cur else {}))
        inst += r.get("list") or []; cur = r.get("nextPageCursor") or ""
        if not cur: break
    kand = {i["symbol"]: int(i.get("launchTime") or 0) for i in inst if i.get("contractType") == "LinearPerpetual" and i.get("settleCoin") == "USDT"
            and i["symbol"] not in YAKORYA and i["symbol"].endswith("USDT") and int(i.get("launchTime") or 0) < DO - 90 * DEN}
    print("кандидатов:", len(kand), flush=True)
    obor = {}
    for n, s in enumerate(sorted(kand), 1):
        d = kesh(f"d1_{s}", lambda s=s: kline(s, "D", OT - 2 * DEN, DO, DEN))
        obor[s] = {x[0]: x[6] for x in d}
        if n % 50 == 0: print("D1", n, len(kand), flush=True)
    vselennaya = {}
    for d in range(OT, DO, DEN):
        el = [(obor[s].get(d - DEN, 0), s) for s in kand if d - kand[s] >= 90 * DEN and obor[s].get(d - DEN, 0) >= 2e7]
        vselennaya[d] = {s for _, s in sorted(el, reverse=True)[:8]}
    nuzhny = sorted(set().union(*vselennaya.values()) - set(F.NE_HVOST));   # события только по хвосту, как у судьи print("монет во вселенной за период:", len(nuzhny), flush=True)
    btc = {x[0]: x for x in kesh("h1_BTC", lambda: kline("BTCUSDT", "60", OT, DO + 2 * DEN, H))}
    sob = []
    for s in nuzhny:
        fd = kesh(f"f_{s}", lambda s=s: fanding(s, OT - 60 * DEN, DO))
        ts_ = [t for t, _ in fd]
        for k, (t, rt) in enumerate(fd):
            if not (OT <= t < DO) or s not in vselennaya.get(t // DEN * DEN, ()): continue
            if k < 90: continue
            prior = sorted(v for _, v in fd[k - 90:k]); hi = prior[min(89, int(90 * 0.70))]
            if rt > hi and rt > 0: sob.append((t, s))
    sob.sort(); print("сигналов до лимитов:", len(sob), flush=True)
    otkr, sd = [], []
    h1 = {}
    for t, s in sob:
        otkr = [o for o in otkr if o[0] > t]
        if len(otkr) >= 3 or any(o[1] == s for o in otkr): continue
        if s not in h1: h1[s] = {x[0]: x for x in kesh(f"h1_{s}", lambda s=s: kline(s, "60", OT, DO + 2 * DEN, H))}
        b = h1[s]; t0 = t // H * H
        if t0 not in b or t0 + 15 * H not in b or t0 not in btc or t0 + 15 * H not in btc: continue
        e = b[t0][1]; avar = next((k for k in range(16) if b.get(t0 + k * H, [0, 0, 0])[2] >= e * 1.8), None)
        vyh = e * 1.8 * 1.05 if avar is not None else b[t0 + 15 * H][4]
        fd = kesh(f"f_{s}", lambda: [])
        fund = sum(r for ft, r in fd if t0 < ft <= t0 + 16 * H) * 1e4
        btc_r = (btc[t0 + 15 * H][4] / btc[t0][1] - 1) * 1e4
        net = (e - vyh) / e * 1e4 + fund - 36 + btc_r - 12
        otkr.append((t0 + 16 * H, s)); sd.append(dict(sym=s, ts=t0, net_bps=round(net, 1), d=time.strftime("%Y-%m-%d", time.gmtime(t0 / 1000))))
    if not sd: sys.exit("нет сделок")
    x = [z["net_bps"] for z in sd]; po = collections.defaultdict(list); mes = collections.defaultdict(float); mon = collections.defaultdict(float)
    for z in sd: po[z["d"]].append(z["net_bps"]); mes[z["d"][:7]] += z["net_bps"]; mon[z["sym"]] += z["net_bps"]
    m = [st.mean(v) for v in po.values()]; t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
    bez5 = sum(sorted(x)[:-5]); plus = sum(v for v in mon.values() if v > 0) or 1
    out = dict(sobytiy=len(sd), sred_bps=round(st.mean(x), 1), med_bps=round(st.median(x), 1), t_dni=round(t, 2) if t else None,
               mesyacy_usd_pri_100={k: round(v / 100, 1) for k, v in sorted(mes.items())}, mesyacev_plus=sum(v > 0 for v in mes.values()),
               bez_5_luchshih_usd=round(bez5 / 100, 1), itogo_usd=round(sum(x) / 100, 1), luchshaya_moneta=max(mon, key=mon.get),
               dolya_luchshey=round(max(mon.values()) / plus, 3))
    out["vyvod"] = "REGULYAREN" if (len(sd) >= 100 and out["sred_bps"] > 0 and (t or 0) >= 2 and out["mesyacev_plus"] >= 6 and bez5 > 0) else "NE_REGULYAREN"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("short_hvost_istoriya_2025_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(out, sdelki=sd), ensure_ascii=False))

if __name__ == "__main__":
    main()
