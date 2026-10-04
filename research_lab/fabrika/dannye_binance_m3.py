#!/usr/bin/env python3
"""dannye_binance_m3.py — дневные свечи с колонками тейкеров для PREREG_KITY_M3_POTOK_2026_10_04.md (до данных).
Монеты — те, что хоть раз были в PIT топ-50 KITY (data/binance_kity/metrics). Храним [ts, quote_volume, taker_buy_quote].
Самопроверка BTCUSDT 2023-01: 31 бар и доля тейкеров в (0, 1) — иначе СТОП. Возобновляемо.

    python3 research_lab/fabrika/dannye_binance_m3.py
"""
import datetime as dt, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dannye_binance as B

K = Path(__file__).resolve().parent.parent / "data" / "binance_kity"
OUT = K / "taker"
MES = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13) if "2021-04" <= f"{y}-{m:02d}" <= "2026-09"]


def razobrat(b):
    out = []
    for r in B.csv_iz_zip(b):
        if r and r[0].strip().isdigit() and len(r) >= 11:
            qv, tq = B.fl(r[7]), B.fl(r[10])
            if qv is not None and tq is not None:
                out.append([int(r[0]), qv, tq])
    return out


def main():
    p = razobrat(B.get(B.url_k("BTCUSDT", "2023-01")))
    print("самопроверка BTCUSDT 2023-01:", len(p), "баров, первый", p[:1])
    if len(p) != 31 or not all(0 < x[2] / x[1] < 1 for x in p if x[1]):
        sys.exit("СТОП: формат колонок тейкеров не тот")
    oi = {}
    for f in (K / "metrics").glob("*.json"):
        for d, v in json.loads(f.read_text()).items():
            if v[4]:
                oi.setdefault(d, []).append((v[4], f.stem))
    sim = sorted({s for d in oi for _, s in sorted(oi[d], reverse=True)[:50]})
    print(f"монет: {len(sim)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for n, s in enumerate(sim, 1):
        f = OUT / f"{s}.json"
        if f.exists():
            continue
        with ThreadPoolExecutor(B.POTOKI) as ex:
            bb = list(ex.map(lambda m: B.get(B.url_k(s, m)), MES))
        rows = sorted({r[0]: r for b in bb if b for r in razobrat(b)}.values())
        f.write_text(json.dumps(rows)); print(f"[{n}/{len(sim)}] {s}: {len(rows)} баров", flush=True)
    (K / "taker_gotovo.json").write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                                          monet=len(sim)), indent=1))
    print("ГОТОВО")


if __name__ == "__main__":
    main()
