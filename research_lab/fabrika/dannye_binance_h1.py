#!/usr/bin/env python3
"""dannye_binance_h1.py — часовые свечи Binance USD-M c агрессивным потоком (data.binance.vision, monthly klines 1h), 14.10.2026.
Для PREREG_POGLOSHCHENIE_H1_2026_10_14: в свече Binance есть объём в $ и объём агрессивных покупок в $ (taker buy quote) —
это агрегат aggTrades по часу, без скачивания тиков. Монеты: все, кто был в PIT топ-50 по OI (недельные снимки) 2021-07…2026-09;
месяцы: от (первого попадания − 2 мес., для 30-дневной истории) до последнего. Храним [ts_open, open, close, quote_vol, taker_buy_quote].
Возобновляемо; 404 → месяц пропущен (монета ещё не торговалась).
    .venv/bin/python research_lab/fabrika/dannye_binance_h1.py           # на Маке, в screen
"""
import datetime as dt, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent; LAB = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(LAB))
import dannye_binance as B          # noqa: E402

OUT = LAB / "data" / "binance_h1"


def url(s, m): return f"{B.ARH}data/futures/um/monthly/klines/{s}/1h/{s}-1h-{m}.zip"


def mesyacy(a, b):
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out


def razobrat(b):
    out = []
    for r in B.csv_iz_zip(b):
        if r and r[0].strip().isdigit() and len(r) >= 11:
            out.append([int(r[0]), float(r[1]), float(r[4]), float(r[7]), float(r[10])])
    return out


def vselennaya():
    import kity_sudya as K
    M = K.zagruzit(); per = {}
    for s, x in M.items():
        for vch, v in x["met"].items():
            if v[4]: per.setdefault(vch, []).append((v[4], s))
    gran = {}
    for vch, lst in per.items():
        d = dt.date.fromisoformat(vch)
        if not (dt.date(2021, 7, 1) <= d <= dt.date(2026, 9, 30)): continue
        for _, s in sorted(lst, reverse=True)[:50]:
            a, b = gran.get(s, (d, d)); gran[s] = (min(a, d), max(b, d))
    return gran


def simvol(s, a, b):
    p = OUT / f"{s}.json"; gotovye = OUT / "gotovo" / s
    if gotovye.exists(): return 0
    nach = (a.replace(day=1) - dt.timedelta(days=62)); ms = mesyacy(nach, b + dt.timedelta(days=8))
    def odin(m):
        x = B.get(url(s, m)); return razobrat(x) if x else []
    with ThreadPoolExecutor(B.POTOKI) as ex: rows = sorted({r[0]: r for ch in ex.map(odin, ms) for r in ch}.values())
    p.write_text(json.dumps(rows)); gotovye.parent.mkdir(parents=True, exist_ok=True); gotovye.write_text(str(len(rows)))
    return len(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True); t0 = time.time()
    test = B.get(url("BTCUSDT", "2024-06"))
    if not test: sys.exit("СТОП: нет BTCUSDT 1h 2024-06")
    r = razobrat(test); print("формат:", r[:2], "строк", len(r), flush=True)
    if len(r) < 700 or not (0 < r[0][4] < r[0][3]): sys.exit("СТОП: неожиданный формат (taker_buy_quote должен быть < quote_vol)")
    G = vselennaya(); print("монет", len(G), flush=True)
    for k, s in enumerate(sorted(G), 1):
        n = simvol(s, *G[s]); print(f"{k}/{len(G)} {s}: часов {n}, {time.time() - t0:.0f} с", flush=True)
    (OUT / "GOTOVO.json").write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(), monet=len(G))))
    print("ГОТОВО", flush=True)


if __name__ == "__main__":
    main()
