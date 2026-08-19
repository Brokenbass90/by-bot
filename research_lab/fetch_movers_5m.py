"""Скачивание 5m-истории СВЕЖИХ листингов/movers Bybit (Mac, ~20-40 мин, resumable).

Зачем: скриншот-сетапы (BANK/POLYX/ESPORTS...) живут на свежих монетах, а не на majors —
это дважды доказано станциями. Скачиваем 5m ВСЕХ USDT-перпов, залистанных за последние
18 месяцев (без отбора по сегодняшнему объёму, чтобы меньше survivorship-bias; делистнутые
недоступны — честно помним об этом ограничении).

    cd <repo> && source .venv/bin/activate
    nohup python3 research_lab/fetch_movers_5m.py > research_lab/results/movers_fetch.log 2>&1 &
    tail -f research_lab/results/movers_fetch.log
"""
from __future__ import annotations
import json, os, time

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_HERE, "data", "movers_5m")
os.makedirs(OUT, exist_ok=True)
BASE = "https://api.bybit.com"
MAX_AGE_DAYS = 548          # листинги за ~18 месяцев
MAX_HISTORY_DAYS = 400      # качаем максимум ~13 месяцев истории
EXTRA = ["BANKUSDT", "POLYXUSDT", "ESPORTSUSDT", "AKEUSDT", "LYNUSDT"]  # со скриншотов


def all_linear_symbols():
    out, cursor = [], ""
    while True:
        p = {"category": "linear", "limit": 1000}
        if cursor:
            p["cursor"] = cursor
        r = requests.get(f"{BASE}/v5/market/instruments-info", params=p, timeout=15).json()
        res = r.get("result") or {}
        for it in res.get("list") or []:
            out.append(it)
        cursor = res.get("nextPageCursor") or ""
        if not cursor:
            return out


def fetch_5m(sym, start_ms):
    rows = {}
    end = None
    for _ in range(150):
        p = {"category": "linear", "symbol": sym, "interval": "5", "limit": 1000}
        if end:
            p["end"] = end
        r = requests.get(f"{BASE}/v5/market/kline", params=p, timeout=15).json()
        lst = (r.get("result") or {}).get("list") or []
        if not lst:
            break
        for it in lst:
            ts = int(it[0])
            if ts >= start_ms:
                rows[ts] = [ts, float(it[1]), float(it[2]), float(it[3]),
                            float(it[4]), float(it[5])]
        oldest = min(int(it[0]) for it in lst)
        if oldest <= start_ms or len(lst) < 1000:
            break
        end = oldest - 1
        time.sleep(0.12)
    return [rows[k] for k in sorted(rows)]


if __name__ == "__main__":
    now = time.time() * 1000
    info = all_linear_symbols()
    fresh = []
    for it in info:
        sym = it.get("symbol") or ""
        if not sym.endswith("USDT") or it.get("status") != "Trading":
            continue
        lt = int(it.get("launchTime") or 0)
        age_d = (now - lt) / 86400000.0 if lt else 1e9
        if age_d <= MAX_AGE_DAYS or sym in EXTRA:
            fresh.append((sym, lt))
    print(f"свежих листингов (<= {MAX_AGE_DAYS}д) + extra: {len(fresh)}")
    done = 0
    for sym, lt in sorted(fresh, key=lambda x: x[1]):
        path = os.path.join(OUT, f"{sym}.json")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            done += 1
            continue
        start = max(lt, now - MAX_HISTORY_DAYS * 86400000.0)
        try:
            rows = fetch_5m(sym, int(start))
        except Exception as e:
            print(f"{sym}: ошибка {e}")
            continue
        json.dump(rows, open(path, "w"))
        done += 1
        print(f"[{done}/{len(fresh)}] {sym}: {len(rows)} баров 5m", flush=True)
    print("ГОТОВО: данные в research_lab/data/movers_5m/")
