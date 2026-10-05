#!/usr/bin/env python3
"""mt5_glubina_d1.py — проба ГЛУБИНЫ дневной истории MT5 для REBALANCING_PRESSURE. Только чтение, ни одного ордера.
Цены НЕ сохраняются (только число баров, первая/последняя дата) — окна не тратятся. Нужен демо-счёт брокера (не MetaQuotes).
    cd signal_copy && ../.venv/bin/python3 ../research_lab/fabrika/mt5_glubina_d1.py
"""
import datetime as dt, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fx_broker_vygruzka as F

KAND = {"US500": ["US500", "#US500", "SPX500", "USA500"], "NAS100": ["NAS100", "#USNDAQ100", "USTEC", "NDX100"],
        "US30": ["US30", "#USDJ30", "DJ30"], "XAUUSD": ["XAUUSD", "GOLD"], "EURUSD": ["EURUSD"],
        "OBLIGACII": ["USTBOND", "US10Y", "UST10Y", "#US10Y", "TNOTE", "T-NOTE", "US10YR", "BUND", "#BUND", "TLT", "IEF"]}


def glubina(m, imya):
    try:
        m.add_symbol(imya)
    except F.MT5Error:
        pass
    vse = set()
    for god in range(2000, dt.date.today().year + 1):
        for p in range(3):
            try:
                r = m.call("get_chart_history", timeout=90.0, symbol=imya, period="D1",
                           datetime_from=f"{god}-01-01T00:00:00", datetime_to=f"{god + 1}-01-01T00:00:00", limit=1000)
            except F.MT5Error:
                break
            bary = F._spisok(r, ("history", "candles", "rates", "bars", "data", "items"))
            if bary:
                vse |= {str(x.get("time") or x.get("datetime"))[:10] for x in bary}; break
            __import__("time").sleep(2)
    return sorted(vse)


def main():
    m = F.MT5MCP(F.config.MT5_URL, F.config.MT5_TOKEN); m.connect()
    server = str(m.account().get("server", "")); print("сервер:", server)
    if "MetaQuotes" in server:
        sys.exit("MetaQuotes-Demo — нужен демо-счёт брокера (FxPro)")
    for s, kk in KAND.items():
        nashel = False
        for k in kk:
            try:
                m.symbol(k)
            except F.MT5Error:
                try:
                    m.add_symbol(k); m.symbol(k)
                except F.MT5Error:
                    continue
            d = glubina(m, k)
            if d:
                print(f"{s} ({k}): дневных баров {len(d)}, с {d[0]} по {d[-1]}", flush=True); nashel = True; break
        if not nashel:
            print(f"{s}: не найден / нет истории (пробовал {kk})")


if __name__ == "__main__":
    main()
