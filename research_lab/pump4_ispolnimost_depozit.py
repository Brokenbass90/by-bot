#!/usr/bin/env python3
"""pump4_ispolnimost_depozit.py — PUMP4 на депозите $1 000 при риске $10 (и $3, $5) с реальными ограничениями (27.10.2026, Claude; задание PM).
Только чтение публичного REST Bybit (Mac). По каждой из закрытых сделок непрерывного повтора (results/pump4_polnyy_povtor_*.json):
  вход = open следующего часа; стоп = risk_pct; qty = (риск $ / стоп $) вниз до qtyStep; исполнимо, если qty ≥ minOrderQty и qty·цена ≥ minNotionalValue;
  фандинг Bybit за удержание (шорт получает при положительной ставке); проскальзывание 5 и 15 bps на сторону (сверх комиссий в R);
  маржа: изолированная, плечо min(10, maxLeverage); депозит $1 000; одновременные позиции — хронологически; лимит суммарной маржи $1 000.
Печатает: исполнимых сделок, net-PnL ($ и % за период и в год — экстраполяция помечена), макс. просадку, фандинг, проскальзывание, пик маржи,
отдельно без 5 лучших сделок.    .venv/bin/python3 research_lab/pump4_ispolnimost_depozit.py"""
import glob, json, math, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; H = 3600000

def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r: return json.loads(r.read())

def main():
    f = sorted(glob.glob(str(HERE / "results" / "pump4_polnyy_povtor_*.json")))[-1]
    S = sorted([x for x in json.load(open(f))["sdelki"] if x.get("status") == "ZAKRYTA" and x.get("R") is not None], key=lambda x: x["ts"])
    inst = {}
    cur = ""
    while True:
        r = get("https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000" + (f"&cursor={cur}" if cur else ""))["result"]
        for i in r["list"]:
            lf = i["lotSizeFilter"]; inst[i["symbol"]] = dict(minq=float(lf["minOrderQty"]), step=float(lf["qtyStep"]),
                minnot=float(lf.get("minNotionalValue") or 0), lev=float(i["leverageFilter"]["maxLeverage"]))
        cur = r.get("nextPageCursor") or ""
        if not cur: break
    dan = []
    for x in S:
        try:
            k = get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={x['sym']}&interval=60&start={x['ts'] + H}&end={x['ts'] + H}&limit=1")["result"]["list"]
            fd = get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={x['sym']}&startTime={x['ts'] + H}&endTime={x['ts'] + (x['barov'] + 2) * H}&limit=200")["result"]["list"]
            time.sleep(0.12)
        except Exception as e: print("!", x["sym"], str(e)[:60]); continue
        if not k: continue
        dan.append(dict(x, vhod=float(k[0][1]), fund=sum(float(z["fundingRate"]) for z in fd)))
    print("сделок с данными:", len(dan), "из", len(S), "период дней:", round((max(d["ts"] for d in dan) - min(d["ts"] for d in dan)) / 864e5, 1))
    for X in (3, 5, 10):
        for slip in (5, 15):
            dep = 1000.0; otkr = []; ev = []; isp = prop_lot = prop_marzh = 0; fund_usd = slip_usd = 0.0; pik_m = 0
            for d in dan:
                ii = inst.get(d["sym"])
                if not ii: prop_lot += 1; continue
                stop_usd = d["vhod"] * d["risk_pct"] / 100; qty = math.floor(X / stop_usd / ii["step"]) * ii["step"]
                nom = qty * d["vhod"]
                if qty < ii["minq"] or nom < ii["minnot"] or qty <= 0: prop_lot += 1; continue
                lev = min(10.0, ii["lev"]); m = nom / lev
                otkr = [o for o in otkr if o[0] > d["ts"]]
                if sum(o[1] for o in otkr) + m > dep: prop_marzh += 1; continue
                kon = d["ts"] + (d["barov"] + 2) * H; otkr.append((kon, m)); pik_m = max(pik_m, sum(o[1] for o in otkr))
                risk_fact = qty * stop_usd                                   # фактический риск после округления лота
                fu = d["fund"] * nom; sl = 2 * slip / 1e4 * nom
                ev.append((kon, d["R"] * risk_fact + fu - sl, d["R"] * risk_fact)); isp += 1; fund_usd += fu; slip_usd += sl
            def itog(evs):
                eq = pik = dep; dd = 0
                for _, v, _ in sorted(evs): eq += v; pik = max(pik, eq); dd = max(dd, pik - eq)
                return sum(v for _, v, _ in evs), dd
            pnl, dd = itog(ev); top = sorted(ev, key=lambda e: -e[2])[5:]; pnl5, dd5 = itog(top)
            dni = (max(d["ts"] for d in dan) - min(d["ts"] for d in dan)) / 864e5 + 3
            print(f"риск ${X}, проскальзывание {slip} bps/сторона: исполнимо {isp}, мимо по лоту {prop_lot}, по марже {prop_marzh}; "
                  f"net ${pnl:.0f} за {dni:.0f} дн (экстраполяция ${pnl * 365 / dni:.0f}/год = {pnl * 365 / dni / 10:.0f} %), просадка ${dd:.0f}; "
                  f"фандинг ${fund_usd:+.0f}, проскальзывание −${slip_usd:.0f}, пик маржи ${pik_m:.0f}; без 5 лучших: net ${pnl5:.0f}, просадка ${dd5:.0f}")

if __name__ == "__main__":
    main()
