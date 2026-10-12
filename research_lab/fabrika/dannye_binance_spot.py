#!/usr/bin/env python3
"""dannye_binance_spot.py — дневные СПОТОВЫЕ свечи Binance с колонками тейкеров для PREREG_SPOT_POTOK_TEZIS_2026_10_12.md.
Монеты — те же, что KITY M3 (data/binance_kity/taker/*.json); спот-имя: точное, иначе без префикса 10…0. Храним [ts_ms, quote_volume,
taker_buy_quote]. Спот с 2025-01 пишет время в микросекундах → нормализуем в мс. Самопроверки: BTCUSDT 2023-01 и 2025-01 —
по 31 бару, ts в мс, доля тейкеров в (0, 1) — иначе СТОП. Возобновляемо. Запуск на Mac (нужна сеть):

    .venv/bin/python research_lab/fabrika/dannye_binance_spot.py
"""
import datetime as dt, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dannye_binance as B

K = Path(__file__).resolve().parent.parent / "data" / "binance_kity"
OUT = K / "spot_taker"
MES = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13) if "2021-04" <= f"{y}-{m:02d}" <= "2026-09"]


def url_spot(s, m): return f"{B.ARH}data/spot/monthly/klines/{s}/1d/{s}-1d-{m}.zip"


def spot_imena(perp):
    """Сначала точное имя (на споте бывают 1000SATS, 1000CAT), затем без префикса 10…0 (PEPE, SHIB, BONK)."""
    bez = re.sub(r"^10+(?=[A-Z])", "", perp)
    return [perp] + ([bez] if bez != perp else [])


def razobrat(b):
    out = []
    for r in B.csv_iz_zip(b):
        if r and r[0].strip().isdigit() and len(r) >= 11:
            ts = int(r[0]); ts = ts // 1000 if ts > 10 ** 14 else ts
            qv, tq = B.fl(r[7]), B.fl(r[10])
            if qv is not None and tq is not None:
                out.append([ts, qv, tq])
    return out


def samoproverka(m):
    p = razobrat(B.get(url_spot("BTCUSDT", m)))
    print(f"самопроверка BTCUSDT {m}:", len(p), "баров, первый", p[:1])
    if len(p) != 31 or not all(10 ** 12 < x[0] < 10 ** 13 for x in p) or not all(0 < x[2] / x[1] < 1 for x in p if x[1]):
        sys.exit(f"СТОП: формат спота {m} не тот")


def main():
    samoproverka("2023-01"); samoproverka("2025-01")
    perps = sorted(f.stem for f in (K / "taker").glob("*.json"))
    print(f"монет: {len(perps)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True); net = []
    for n, p in enumerate(perps, 1):
        f = OUT / f"{p}.json"
        if f.exists():
            continue
        rows, s = [], p
        for s in spot_imena(p):
            with ThreadPoolExecutor(B.POTOKI) as ex:
                bb = list(ex.map(lambda m: B.get(url_spot(s, m)), MES))
            rows = sorted({r[0]: r for b in bb if b for r in razobrat(b)}.values())
            if rows:
                break
        if not rows: net.append(p)
        f.write_text(json.dumps(rows)); print(f"[{n}/{len(perps)}] {p} → {s}: {len(rows)} баров", flush=True)
    (K / "spot_taker_gotovo.json").write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                                               monet=len(perps), bez_spota=net), indent=1, ensure_ascii=False))
    print("ГОТОВО", len(perps), "без спота:", len(net))


if __name__ == "__main__":
    main()
