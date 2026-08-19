"""Скачивание ДНЕВОК Bybit с 2020 для TSM-holdout (запуск на Mac, ~1 минута).

Публичный REST, ключи не нужны. Сохраняет research_lab/data/daily_{sym}.json
(строки [ts,o,h,l,c,v], по возрастанию, дедуп). Можно запускать параллельно
со станцией sloped_v1 — нагрузка ничтожная.

    cd <repo> && source .venv/bin/activate
    python3 research_lab/fetch_daily_history.py
"""
from __future__ import annotations
import json, os, time

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_HERE, "data")
os.makedirs(OUT, exist_ok=True)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
           "LINKUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT", "BNBUSDT",
           "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "TONUSDT",
           "TRXUSDT", "MATICUSDT", "FILUSDT", "INJUSDT", "SEIUSDT", "TIAUSDT"]
URL = "https://api.bybit.com/v5/market/kline"


def fetch_all(sym: str) -> list[list[float]]:
    rows: dict[int, list[float]] = {}
    end = None
    for _ in range(20):  # максимум 20 страниц по 1000 дней
        params = {"category": "linear", "symbol": sym, "interval": "D", "limit": 1000}
        if end is not None:
            params["end"] = end
        r = requests.get(URL, params=params, timeout=15)
        r.raise_for_status()
        lst = (r.json().get("result") or {}).get("list") or []
        if not lst:
            break
        for it in lst:  # bybit отдаёт новые->старые: [start,o,h,l,c,v,turnover]
            ts = int(it[0])
            rows[ts] = [ts, float(it[1]), float(it[2]), float(it[3]),
                        float(it[4]), float(it[5])]
        oldest = min(int(it[0]) for it in lst)
        if len(lst) < 1000:
            break
        end = oldest - 1
        time.sleep(0.25)
    return [rows[k] for k in sorted(rows)]


if __name__ == "__main__":
    for sym in SYMBOLS:
        data = fetch_all(sym)
        path = os.path.join(OUT, f"daily_{sym}.json")
        with open(path, "w") as f:
            json.dump(data, f)
        if data:
            import datetime
            a = datetime.datetime.utcfromtimestamp(data[0][0] / 1000).date()
            b = datetime.datetime.utcfromtimestamp(data[-1][0] / 1000).date()
            print(f"{sym}: {len(data)} дневок  {a} -> {b}  -> {path}")
        else:
            print(f"{sym}: ПУСТО")
