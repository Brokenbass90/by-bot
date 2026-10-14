#!/usr/bin/env python3
"""dannye_binance_glubina.py — история СТАКАНА Binance USD-M (data.binance.vision bookDepth, без ключей), 14.10.2026.

Новый класс данных для фабрики (до сих пор стакан на истории не проверялся ни разу; ORDER_BOOK_IMBALANCE на кладбище —
событие-гэп старого генератора, не стакан). Экономно, как dannye_binance_kity: только дни сигнала недельной сетки KITY
(d−1, 2023-01-04 … 2026-09-16) и только монеты PIT топ-50 по OI в этот день (≈ 9 700 файлов, ≈ 4.3 ГБ трафика; zip не храним).
Из файла дня → признаки (всё за день d−1, до входа):
  imb{1,2,5}       — среднее за день (bid − ask)/(bid + ask) по notional в пределах ±p% от цены;
  imb{1,5}_posl    — то же на последнем снимке дня;  lik{1,5} — среднее (bid + ask) notional в ±p%, $;  n — снимков.
Самопроверка формата на первом файле: нет колонок percentage/notional → СТОП с выводом первых строк.
Возобновляемо (готовые дни пропускаются), 12 потоков, 404 → день отмечается как null.
    .venv/bin/python research_lab/fabrika/dannye_binance_glubina.py            # на Маке, в screen (ниже)
"""
import datetime as dt, json, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent; LAB = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(LAB))
import dannye_binance as B          # noqa: E402  (get / csv_iz_zip — те же, что у загрузки KITY)

OUT = LAB / "data" / "binance_glubina"
NACH, KON = dt.date(2023, 1, 2), dt.date(2026, 9, 30)


def url(s, d): return f"{B.ARH}data/futures/um/daily/bookDepth/{s}/{s}-bookDepth-{d}.zip"


def pary():
    import kity_sudya as K
    M = K.zagruzit(); out = defaultdict(set)
    for d in K.SETKA:
        if not (NACH <= d <= KON): continue
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        for _, s in oi: out[s].add(vch)
    return out


def priznaki(rows):
    h = [c.strip().lower() for c in rows[0]]
    if "percentage" not in h or not ("notional" in h or "depth" in h):
        raise SystemExit(f"СТОП: неожиданный формат bookDepth: {rows[:5]}")
    it, ip, iv = h.index("timestamp") if "timestamp" in h else 0, h.index("percentage"), h.index("notional" if "notional" in h else "depth")
    sn = defaultdict(dict)                                   # ts → {percent: notional}
    for r in rows[1:]:
        p, v = B.fl(r[ip]), B.fl(r[iv])
        if p is None or v is None: continue
        sn[r[it]][round(p, 2)] = v
    imb = {1: [], 2: [], 5: []}; lik = {1: [], 5: []}; posl = None
    for ts in sorted(sn):
        q = sn[ts]; ok = False
        for p in (1, 2, 5):
            b, a = q.get(-float(p)), q.get(float(p))
            if b is None or a is None or b + a <= 0: continue
            imb[p].append((b - a) / (b + a)); ok = True
            if p in lik: lik[p].append(b + a)
        if ok: posl = q
    if not imb[1]: return None
    def m(x): return round(sum(x) / len(x), 6) if x else None
    def im(q, p):
        b, a = q.get(-float(p)), q.get(float(p))
        return round((b - a) / (b + a), 6) if b is not None and a is not None and b + a > 0 else None
    return dict(n=len(imb[1]), imb1=m(imb[1]), imb2=m(imb[2]), imb5=m(imb[5]), imb1_posl=im(posl, 1), imb5_posl=im(posl, 5),
                lik1=m(lik[1]), lik5=m(lik[5]))


def simvol(s, dni):
    p = OUT / f"{s}.json"; uzhe = json.loads(p.read_text()) if p.exists() else {}
    nado = sorted(d for d in dni if d not in uzhe)
    def odin(d):
        b = B.get(url(s, d)); return d, (priznaki(B.csv_iz_zip(b)) if b else None)
    with ThreadPoolExecutor(B.POTOKI) as ex:
        for d, v in ex.map(odin, nado): uzhe[d] = v
    if nado: p.write_text(json.dumps(uzhe, sort_keys=True))
    return len(nado), sum(v is not None for v in uzhe.values())


def main():
    OUT.mkdir(parents=True, exist_ok=True); t0 = time.time()
    b = B.get(url("BTCUSDT", "2024-06-04"))
    if not b: sys.exit("СТОП: нет тестового файла BTCUSDT 2024-06-04 — архив недоступен")
    rows = B.csv_iz_zip(b); print("формат:", rows[:3], "→", priznaki(rows), flush=True)
    P = pary(); vsego = sum(len(v) for v in P.values()); print(f"монет {len(P)}, файлов {vsego}", flush=True)
    for k, s in enumerate(sorted(P), 1):
        novyh, est = simvol(s, P[s])
        print(f"{k}/{len(P)} {s}: скачано {novyh}, с данными {est}/{len(P[s])}, {time.time() - t0:.0f} с", flush=True)
    (OUT / "GOTOVO.json").write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(), monet=len(P), faylov=vsego)))
    print("ГОТОВО", flush=True)


if __name__ == "__main__":
    main()
