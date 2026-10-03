#!/usr/bin/env python3
"""dannye_binance_kity.py — загрузка для PREREG_KITY_POZICII_2026_10_03.md. Закоммичено ДО скачивания.

Экономно: нужен только один дневной файл metrics на символ на неделю — день d−1 недельной сетки
(2021-07-01 + 7k, вход ≤ 2026-09-23). Из файла: в 00:00 (первая точка в [00:00, 00:15]) —
[толпа count_long_short_ratio, M2 sum_toptrader, M1 count_toptrader, M3 sum_taker] и OI $ в 23:55 ([23:40, 23:55]).
Фаза 2: монеты, хоть раз попавшие в PIT топ-50 по OI, → klines 1d (2021-04…2026-09) и fundingRate (2021-06…2026-09).
Самопроверка: BTCUSDT metrics, klines 2026-09 и funding 2026-09 должны существовать — иначе СТОП (месяц ещё не выложен).
Возобновляемо. Использует функции dannye_binance.py.

    python3 research_lab/fabrika/dannye_binance_kity.py
"""
import datetime as dt, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dannye_binance as B

D = Path(__file__).resolve().parent.parent / "data" / "binance_kity"
NACH, KON = dt.date(2021, 7, 1), dt.date(2026, 9, 23)
SETKA = [NACH + dt.timedelta(days=7 * k) for k in range(400) if NACH + dt.timedelta(days=7 * k) <= KON]
NUZHNY = {(d - dt.timedelta(days=1)).isoformat() for d in SETKA}
K_MES = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13) if "2021-04" <= f"{y}-{m:02d}" <= "2026-09"]
F_MES = [m for m in K_MES if m >= "2021-06"]
KOL = ("count_long_short_ratio", "sum_toptrader_long_short_ratio", "count_toptrader_long_short_ratio",
       "sum_taker_long_short_vol_ratio")


def razobrat(b):
    rows = B.csv_iz_zip(b); h = rows[0]
    ic, io_ = h.index("create_time"), h.index("sum_open_interest_value"); ik = [h.index(k) for k in KOL]
    toch = []
    for r in rows[1:]:
        try:
            t = dt.datetime.strptime(r[ic][:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        toch.append((t.hour * 60 + t.minute, r))
    toch.sort(key=lambda p: p[0])
    rano = [r for m, r in toch if 0 <= m <= 15]
    vecher = [r for m, r in toch if 23 * 60 + 40 <= m <= 23 * 60 + 55]
    pr = [next((B.fl(r[i]) for r in rano if B.fl(r[i]) is not None), None) for i in ik]
    oi = next((B.fl(r[io_]) for r in reversed(vecher) if B.fl(r[io_]) is not None), None)
    return pr + [oi]


def proverka():
    m = razobrat(B.get(B.url_m("BTCUSDT", "2025-06-01")))
    k = B.get(B.url_k("BTCUSDT", "2026-09")); f = B.get(B.url_f("BTCUSDT", "2026-09"))
    print("самопроверка: BTCUSDT 2025-06-01 [толпа, M2, M1, M3, OI] =", m)
    if None in m:
        sys.exit("СТОП: разбор metrics не прошёл")
    if not k or not f:
        sys.exit("СТОП: месячные файлы 2026-09 ещё не выложены — повторить через день-два")
    print(f"  klines 2026-09: {len(B.klines_mes(k))} баров; funding 2026-09: {len(B.funding_mes(f))} ставок — OK")


def metrics_simvola(s):
    gf = D / "gotovo_m" / s
    if gf.exists():
        return json.loads(gf.read_text())
    est = set()
    for god in range(2021, 2027):
        _, kl = B.listing(f"data/futures/um/daily/metrics/{s}/{s}-metrics-{god}-")
        est |= {m.group(1) for k in kl for m in [re.search(r"metrics-(\d{4}-\d\d-\d\d)\.zip$", k)] if m}
    dni = sorted(est & NUZHNY); met = {}
    if dni:
        def odin(d):
            b = B.get(B.url_m(s, d)); return d, (razobrat(b) if b else None)
        with ThreadPoolExecutor(B.POTOKI) as ex:
            met = {d: v for d, v in ex.map(odin, dni) if v}
        (D / "metrics").mkdir(parents=True, exist_ok=True)
        (D / "metrics" / f"{s}.json").write_text(json.dumps(met))
    res = {"s": s, "dney": len(dni), "ok": len(met)}
    (D / "gotovo_m").mkdir(parents=True, exist_ok=True); gf.write_text(json.dumps(res))
    return res


def ceny(s):
    if (D / "klines" / f"{s}.json").exists() and (D / "funding" / f"{s}.json").exists():
        return
    with ThreadPoolExecutor(B.POTOKI) as ex:
        kl = list(ex.map(lambda m: B.get(B.url_k(s, m)), K_MES))
        fr = list(ex.map(lambda m: B.get(B.url_f(s, m)), F_MES))
    kl = sorted({r[0]: r for b in kl if b for r in B.klines_mes(b)}.values())
    fr = sorted({r[0]: r for b in fr if b for r in B.funding_mes(b)}.values())
    for pap, obj in (("klines", kl), ("funding", fr)):
        (D / pap).mkdir(parents=True, exist_ok=True); (D / pap / f"{s}.json").write_text(json.dumps(obj))


def main():
    proverka()
    papki, _ = B.listing("data/futures/um/daily/metrics/")
    sim = sorted({p.rstrip("/").split("/")[-1] for p in papki})
    sim = [s for s in sim if s.endswith("USDT") and "_" not in s]
    print(f"символов: {len(sim)}; недель в сетке: {len(SETKA)}", flush=True)
    for n, s in enumerate(sim, 1):
        print(f"[M {n}/{len(sim)}] {metrics_simvola(s)}", flush=True)
    oi = {}
    for f in (D / "metrics").glob("*.json"):
        for d, v in json.loads(f.read_text()).items():
            if v[4]:
                oi.setdefault(d, []).append((v[4], f.stem))
    kogda_top = sorted({s for d in oi for _, s in sorted(oi[d], reverse=True)[:50]})
    print(f"монет, хоть раз в топ-50: {len(kogda_top)}", flush=True)
    for n, s in enumerate(kogda_top, 1):
        ceny(s); print(f"[C {n}/{len(kogda_top)}] {s}", flush=True)
    (D / "gotovo.json").write_text(json.dumps(dict(
        kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), simvolov=len(sim),
        dat_s_oi=len(oi), monet_v_top50=len(kogda_top)), indent=1))
    print("ГОТОВО:", (D / "gotovo.json").read_text())


if __name__ == "__main__":
    main()
