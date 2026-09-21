#!/usr/bin/env python3
"""dannye_pit_kripto.py — скачать дневные свечи и фандинг для PIT-вселенной крипты.

Только публичные данные Bybit (без ключей, без ордеров). Запускать на Mac:
    python3 dannye_pit_kripto.py
Кладёт research_lab/data/pit_daily/<SYMBOL>.json. Уже скачанные пропускает.
    python3 dannye_pit_kripto.py --vse    все ~750 инструментов с суточным OI (≈30–60 мин)
Делистингованные контракты биржа может не отдавать — такие попадут в
pit_daily/_net_dannyh.json, и прогонщик честно покажет недостающее покрытие.
"""
import json, os, time, urllib.request, urllib.parse
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "data/pit_daily"; OUT.mkdir(exist_ok=True)
BASE = "https://api.bybit.com/v5/market/"
START = 1672531200000  # 2023-01-01


def get(path, **q):
    url = BASE + path + "?" + urllib.parse.urlencode(q)
    for popytka in range(4):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.loads(r.read())
            if d.get("retCode") == 0:
                return d["result"]
            if d.get("retCode") in (10006, 10018):
                time.sleep(2); continue
            return None
        except Exception:
            time.sleep(2)
    return None


def svechi(sym):
    out, end = {}, int(time.time() * 1000)
    while end > START:
        r = get("kline", category="linear", symbol=sym, interval="D", start=START, end=end, limit=1000)
        rows = (r or {}).get("list") or []
        if not rows:
            break
        for x in rows:
            out[int(x[0])] = [int(x[0])] + [float(v) for v in x[1:6]]
        oldest = min(int(x[0]) for x in rows)
        if oldest >= end:
            break
        end = oldest - 1; time.sleep(0.12)
    return [out[k] for k in sorted(out)]


def fanding(sym):
    out, end = {}, int(time.time() * 1000)
    while end > START:
        r = get("funding/history", category="linear", symbol=sym, startTime=START, endTime=end, limit=200)
        rows = (r or {}).get("list") or []
        if not rows:
            break
        for x in rows:
            out[int(x["fundingRateTimestamp"])] = float(x["fundingRate"])
        oldest = min(int(x["fundingRateTimestamp"]) for x in rows)
        if oldest >= end:
            break
        end = oldest - 1; time.sleep(0.12)
    return [[k, out[k]] for k in sorted(out)]


def main():
    import sys
    v = json.load(open(LAB / "data/basis/vselennaya_pit.json"))
    net = []
    simvoly = sorted(set(v["simvoly"]) | {"BTCUSDT", "ETHUSDT"})   # BTC/ETH нужны метке режима
    if "--vse" in sys.argv:
        # все инструменты, у которых есть суточный OI: нужны цены, чтобы ранжировать OI в ДОЛЛАРАХ
        simvoly = sorted(set(simvoly) | {f.stem for f in (LAB / "data/basis/oi_sutochnyy").glob("*.json")})
    for i, s in enumerate(simvoly):
        p = OUT / f"{s}.json"
        if p.exists():
            continue
        d = svechi(s)
        if not d:
            net.append(s); print(f"{i+1:>3}/{len(simvoly)} {s}: свечей нет"); continue
        f = fanding(s)
        tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps({"symbol": s, "daily": d, "funding": f})); tmp.replace(p)
        print(f"{i+1:>3}/{len(simvoly)} {s}: дней {len(d)}, фандингов {len(f)}", flush=True)
    (OUT / "_net_dannyh.json").write_text(json.dumps(net))
    print("готово. без данных:", net)


if __name__ == "__main__":
    main()
