#!/usr/bin/env python3
"""short_hvost_uderzhanie.py — prereg/PREREG_SHORT_HVOST_UDERZHANIE_2026_10_27.md. Mac (сеть Bybit), ~5 мин. Только чтение.
    .venv/bin/python3 research_lab/short_hvost_uderzhanie.py > research_lab/data/shvost_uderzhanie.log 2>&1"""
import collections, hashlib, json, math, statistics as st, sys, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import fanding_hvost as F
SHA = "8bbe8500670513ac31b2dfac0d9b27a040dae86aa9a103ec2b1517a2129f7baf"; H = 3600000; UD = (16, 24, 32)

def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r: return json.loads(r.read())

def svechi(sym, t0, n):
    l = (get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&start={t0}&end={t0 + n * H}&limit={n + 2}").get("result") or {}).get("list") or []
    return sorted([[int(x[0])] + [float(v) for v in x[1:5]] for x in l])

def fanding(sym, t0, t1):
    l = (get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={sym}&startTime={t0}&endTime={t1}&limit=200").get("result") or {}).get("list") or []
    return [(int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in l]

def t_dni(x):
    po = collections.defaultdict(list)
    for d, v in x: po[d].append(v)
    m = [st.mean(v) for v in po.values()]
    return round(st.mean(m) / (st.stdev(m) / math.sqrt(len(m))), 2) if len(m) > 2 and st.stdev(m) > 0 else None

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_SHORT_HVOST_UDERZHANIE_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    u = {}
    for fn in F.LEDGERY:
        for l in open(F.ROOT / fn):
            r = json.loads(l)
            if r.get("record_type") == "outcome" and r.get("status") == "closed" and r.get("side") == -1 and r.get("symbol") not in F.NE_HVOST:
                u[(r["symbol"], r["event_ts"])] = r
    rows = []
    for (s, t), _ in sorted(u.items(), key=lambda kv: kv[0][1]):
        try:
            b = svechi(s, t, 33); bt = svechi("BTCUSDT", t, 33); fd = fanding(s, t, t + 33 * H); time.sleep(0.15)
        except Exception as e: print("!", s, str(e)[:60], flush=True); continue
        if len(b) < 33 or len(bt) < 33: continue
        e, eb = b[0][1], bt[0][1]; z = dict(sym=s, ts=t, d=time.strftime("%Y-%m-%d", time.gmtime(t / 1000)))
        for h in UD:
            avar = next((k for k in range(h) if b[k][2] >= e * 1.8), None)
            vyh = e * 1.8 * 1.05 if avar is not None else b[h - 1][4]; kon = t + ((avar + 1) if avar is not None else h) * H
            mae = max(x[2] for x in b[:(avar + 1) if avar is not None else h]) / e - 1
            fund = sum(fr for ts_, fr in fd if t < ts_ <= kon) * 1e4                 # шорт получает при положительной ставке
            net = (e - vyh) / e * 1e4 + fund - 36
            btc = (bt[min(h, len(bt)) - 1][4] / eb - 1) * 1e4
            z[h] = dict(net=round(net, 1), net_hedzh=round(net + btc - 12, 1), mae=round(mae * 100, 2), avar=avar is not None, fund=round(fund, 1), kon=kon)
        rows.append(z)
    out = dict(sdelok=len(rows), po_uderzhaniyu={}, parno={})
    for h in UD:
        net = [r[h]["net"] for r in rows]; hed = [r[h]["net_hedzh"] for r in rows]; mae = [r[h]["mae"] for r in rows]
        sob = sorted([(r["ts"], 1) for r in rows] + [(r[h]["kon"], -1) for r in rows]); cur = pik = 0
        for _, d in sob: cur += d; pik = max(pik, cur)
        pos_ch = sum((r[h]["kon"] - r["ts"]) / H for r in rows)
        out["po_uderzhaniyu"][h] = dict(net_sred=round(st.mean(net), 1), net_med=round(st.median(net), 1), hedzh_sred=round(st.mean(hed), 1),
            hedzh_med=round(st.median(hed), 1), fund_sred=round(st.mean(r[h]["fund"] for r in rows), 1), mae_med=round(st.median(mae), 2),
            mae_ge={p: sum(m >= p for m in mae) for p in (30, 50, 80)}, avar_stopov=sum(r[h]["avar"] for r in rows),
            hudshaya_hedzh=round(min(hed), 1), na_poziciyu_chas_bps=round(sum(hed) / pos_ch, 2), pik_pozicyy=pik,
            na_poziciyu_sutki_bps=round(sum(hed) / pos_ch * 24, 1))
    hh = len(rows) // 2
    for h in (24, 32):
        for nm, g in (("vse", rows), ("rannyaya", rows[:hh]), ("pozdnyaya", rows[hh:])):
            d = [r[h]["net_hedzh"] - r[16]["net_hedzh"] for r in g]
            out["parno"][f"{h}_minus_16_{nm}"] = dict(n=len(d), sred=round(st.mean(d), 1), med=round(st.median(d), 1), dolya_plus=round(sum(x > 0 for x in d) / len(d), 3),
                hudshaya=round(min(d), 1), t_dni=t_dni([(r["d"], r[h]["net_hedzh"] - r[16]["net_hedzh"]) for r in g]))
    p = out["parno"]["24_minus_16_pozdnyaya"]; b16, b24 = out["po_uderzhaniyu"][16], out["po_uderzhaniyu"][24]
    ok = p["sred"] > 0 and b24["avar_stopov"] <= b16["avar_stopov"] + 1 and b24["mae_ge"][50] <= b16["mae_ge"][50] + 1
    out["vyvod"] = "24CH_V_PARALLELNUYU_TEN" if ok else "BAZA_16CH"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    f = HERE / "results" / time.strftime("short_hvost_uderzhanie_%Y%m%dT%H%MZ.json", time.gmtime()); f.write_text(json.dumps(dict(out, sdelki=rows), ensure_ascii=False)); print("файл", f)

if __name__ == "__main__":
    main()
