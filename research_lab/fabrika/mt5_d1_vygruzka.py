#!/usr/bin/env python3
"""mt5_d1_vygruzka.py — выгрузка ДНЕВНЫХ свечей MT5 (демо FxPro) для REBALANCING_PRESSURE и будущих механизмов вне крипты.
Только чтение, ни одного ордера. Сохраняет data/mt5_d1/<имя>.json = [[YYYY-MM-DD, o, h, l, c], ...] и печатает покрытие по годам.
До заморозки prereg доходности по этим данным НЕ считаются.
    cd signal_copy && ../.venv/bin/python3 ../research_lab/fabrika/mt5_d1_vygruzka.py
"""
import datetime as dt, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fx_broker_vygruzka as F

OUT = Path(__file__).resolve().parents[1] / "data" / "mt5_d1"
KAND = {"NAS100": ["#USNDAQ100", "NAS100", "USTEC"], "US500": ["#USSPX500", "#SPX500", "US500", "#US500", "SPX500", "USA500", "US500.cash"],
        "US30": ["#USDJ30", "#US30", "US30", "DJ30", "US30.cash"], "GER40": ["#Germany40", "GER40", "#GER40", "DE40"],
        "XAUUSD": ["GOLD", "XAUUSD"], "EURUSD": ["EURUSD"]}


def d1(m, imya):
    try:
        m.add_symbol(imya)
    except F.MT5Error:
        pass
    vse = {}
    for god in range(2000, dt.date.today().year + 1):
        for p in range(3):
            try:
                r = m.call("get_chart_history", timeout=90.0, symbol=imya, period="D1",
                           datetime_from=f"{god}-01-01T00:00:00", datetime_to=f"{god + 1}-01-01T00:00:00", limit=1000)
            except F.MT5Error:
                break
            bary = F._spisok(r, ("history", "candles", "rates", "bars", "data", "items"))
            if bary:
                if not vse:
                    print(f"  {imya}: ключи бара {sorted(bary[0].keys())}", flush=True)
                for x in bary:
                    t = dt.datetime.utcfromtimestamp(F._vremya(x.get("time") or x.get("datetime")) / 1000).date().isoformat()
                    g = lambda *kk: next(float(x[k]) for k in kk if x.get(k) is not None)
                    vse[t] = [t, g("open", "o", "Open"), g("high", "h", "High"), g("low", "l", "Low"), g("close", "c", "Close")]
                break
            __import__("time").sleep(2)
    return [vse[k] for k in sorted(vse)]


def main():
    m = F.MT5MCP(F.config.MT5_URL, F.config.MT5_TOKEN); m.connect()
    server = str(m.account().get("server", "")); print("сервер:", server)
    if "MetaQuotes" in server:
        sys.exit("нужен демо-счёт брокера (FxPro)")
    OUT.mkdir(parents=True, exist_ok=True)
    for s, kk in KAND.items():
        for k in kk:
            try:
                bary = d1(m, k)
            except Exception as e:
                print(f"  {s}/{k}: ошибка {type(e).__name__}: {str(e)[:200]}"); bary = []
            if bary:
                (OUT / f"{s}.json").write_text(json.dumps(dict(simvol=k, server=server, bary=bary)))
                po = {}
                for b in bary:
                    po[b[0][:4]] = po.get(b[0][:4], 0) + 1
                print(f"{s} ({k}): {len(bary)} баров | по годам: " + " ".join(f"{g}:{n}" for g, n in sorted(po.items())), flush=True)
                break
        else:
            print(f"{s}: не найден (пробовал {kk})")


if __name__ == "__main__":
    main()
