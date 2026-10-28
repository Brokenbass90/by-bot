#!/usr/bin/env python3
"""razbor_sbor.py — данные для разбора ВСЕХ сделок PUMP4 и SHORT_HVOST (28.10.2026, Claude; задание PM). Mac (сеть Bybit), ~15–25 мин. Только чтение.
По каждой сделке окно [вход − 72 ч; выход + 24 ч]: H1 перпа, H1 спота (если есть), H1 BTC, открытый интерес 1 ч (Bybit open-interest), фандинг
(история ставок). Ликвидации: у Bybit и Binance нет публичной ИСТОРИИ ликвидаций по REST — не собираем и не подменяем догадками.
Пропуски пишутся как есть (пустые списки). Выход: data/razbor_dannye/<нога>_<монета>_<ts>.json. Повторный запуск докачивает недостающее.
    .venv/bin/python3 research_lab/razbor_sbor.py > research_lab/data/razbor_sbor.log 2>&1"""
import glob, json, time, urllib.parse, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; H = 3600000; OUT = HERE / "data" / "razbor_dannye"; OUT.mkdir(parents=True, exist_ok=True)
API = "https://api.bybit.com/v5/market/"

def get(path, **p):
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path + "?" + urllib.parse.urlencode(p), headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r:
                return (json.loads(r.read()).get("result") or {})
        except Exception:
            time.sleep(1 + k)
    return {}

def kline(cat, sym, t0, t1):
    out, s = [], t0
    while s < t1:
        l = get("kline", category=cat, symbol=sym, interval=60, start=s, end=min(t1, s + 999 * H), limit=1000).get("list") or []
        part = sorted([[int(x[0])] + [float(v) for v in x[1:7]] for x in l])
        if not part: break
        out += [p for p in part if not out or p[0] > out[-1][0]]; s = part[-1][0] + H; time.sleep(0.1)
    return out

def oi(sym, t0, t1):
    out, cur = [], ""
    for _ in range(10):
        r = get("open-interest", category="linear", symbol=sym, intervalTime="1h", startTime=t0, endTime=t1, limit=200, **({"cursor": cur} if cur else {}))
        out += [[int(x["timestamp"]), float(x["openInterest"])] for x in r.get("list") or []]
        cur = r.get("nextPageCursor") or ""
        if not cur: break
        time.sleep(0.1)
    return sorted({x[0]: x for x in out}.values())

def main():
    S = []
    p = json.load(open(sorted(glob.glob(str(HERE / "results" / "pump4_polnyy_povtor_*.json")))[-1]))["sdelki"]
    S += [("PUMP4", x["sym"], x["ts"] + H, x["ts"] + (x["barov"] + 2) * H) for x in p if x.get("R") is not None]
    sh = json.load(open(sorted(glob.glob(str(HERE / "results" / "short_hvost_uderzhanie_*.json")))[-1]))["sdelki"]
    S += [("SHORT_HVOST", x["sym"], x["ts"], x["ts"] + 24 * H) for x in sh]
    for n, (noga, sym, t0, t1) in enumerate(S, 1):
        f = OUT / f"{noga}_{sym}_{t0}.json"
        if f.exists(): continue
        a, b = t0 - 72 * H, t1 + 24 * H
        z = dict(noga=noga, sym=sym, t0=t0, t1=t1, perp=kline("linear", sym, a, b), spot=kline("spot", sym, a, b), btc=kline("linear", "BTCUSDT", a, b),
                 oi=oi(sym, a, b), fanding=[[int(x["fundingRateTimestamp"]), float(x["fundingRate"])] for x in
                                            get("funding/history", category="linear", symbol=sym, startTime=a, endTime=b, limit=200).get("list") or []])
        f.write_text(json.dumps(z))
        if n % 10 == 0: print(n, len(S), sym, "perp", len(z["perp"]), "spot", len(z["spot"]), "oi", len(z["oi"]), "fund", len(z["fanding"]), flush=True)
    print("готово", len(list(OUT.glob("*.json"))), "файлов")

if __name__ == "__main__":
    main()
