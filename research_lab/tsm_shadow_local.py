"""TSM SHADOW (локальный, без сервера) — учёт сигналов tsm4-LS. Денег НЕ трогает.

Запуск раз в неделю (понедельник) на Mac:
    cd <repo> && source .venv/bin/activate && python3 research_lab/tsm_shadow_local.py
Скрипт сам обновляет дневки, считает сигнал L=4w long/short по 5 монетам и дописывает
запись в research_lab/results/tsm_shadow_ledger.jsonl (append-only, с ценами для parity).
Через 8 недель ведём parity-разбор -> решение о canary.
"""
from __future__ import annotations
import json, os, sys, time, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from fetch_daily_history import fetch_all

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "DOGEUSDT"]
LEDGER = os.path.join(_HERE, "results", "tsm_shadow_ledger.jsonl")
L_DAYS = 28

if __name__ == "__main__":
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    prev = None
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                prev = json.loads(line)
            except Exception:
                pass
    rec = {"ts": int(time.time() * 1000),
           "date": datetime.date.today().isoformat(), "signals": {}}
    for s in SYMBOLS:
        rows = fetch_all(s)  # свежие дневки с биржи
        path = os.path.join(_HERE, "data", f"daily_{s}.json")
        json.dump(rows, open(path, "w"))
        closed = rows[:-1]  # последний бар может быть не закрыт
        c, c28 = closed[-1][4], closed[-1 - L_DAYS][4]
        ret = c / c28 - 1.0
        sig = "LONG" if ret > 0 else "SHORT"
        was = (prev or {}).get("signals", {}).get(s, {}).get("signal")
        rec["signals"][s] = {"signal": sig, "ret_4w": round(ret, 4),
                             "close": c, "changed": bool(was and was != sig)}
        flip = "  <-- СМЕНА" if (was and was != sig) else ""
        print(f"{s:10} {sig:5} (4w {ret:+.2%}, close {c}){flip}")
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")
    n = sum(1 for _ in open(LEDGER))
    print(f"-> запись #{n} в {LEDGER}. Следующий запуск: следующий понедельник.")
