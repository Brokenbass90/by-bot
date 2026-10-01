#!/usr/bin/env python3
"""dannye_deribit.py — индекс подразумеваемой волатильности Deribit DVOL (BTC, ETH), класс данных №3 (01.10).
Публичный API Deribit, без ключей, без ордеров. Часовые свечи DVOL с 2021-04 по сегодня.
    python3 dannye_deribit.py        ≈ 1–3 минуты
Кладёт research_lab/data/deribit/dvol_<BTC|ETH>.json: {"ryad": [[ts_ms, open, high, low, close], ...]}
"""
import json, time, urllib.parse, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "data/deribit"; OUT.mkdir(parents=True, exist_ok=True)
URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data?"
START = 1617235200000      # 2021-04-01


def dvol(cur):
    out, end = {}, int(time.time() * 1000)
    while end > START:
        q = urllib.parse.urlencode({"currency": cur, "start_timestamp": START, "end_timestamp": end, "resolution": 3600})
        for popytka in range(4):
            try:
                r = json.loads(urllib.request.urlopen(URL + q, timeout=30).read())["result"]; break
            except Exception:
                time.sleep(3); r = None
        if not r or not r.get("data"):
            break
        for x in r["data"]:
            out[int(x[0])] = [float(v) for v in x[1:5]]
        nxt = r.get("continuation")
        if not nxt or int(nxt) >= end:
            break
        end = int(nxt); time.sleep(0.2)
    return [[k] + out[k] for k in sorted(out)]


if __name__ == "__main__":
    for c in ("BTC", "ETH"):
        d = dvol(c)
        (OUT / f"dvol_{c}.json").write_text(json.dumps({"currency": c, "ryad": d}))
        print(f"DVOL {c}: часов {len(d)}" + (f", с {time.strftime('%Y-%m-%d', time.gmtime(d[0][0] / 1000))}" if d else " — пусто"))
