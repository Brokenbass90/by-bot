#!/usr/bin/env python3
"""
l2_limit_entry.py — сколько на самом деле экономит лимитный вход.

ЗАЧЕМ ЭТО ГЛАВНОЕ СЕЙЧАС. Две ноги подряд показали одно и то же:
отбор работает (контроль даёт ноль), а съедают издержки. У MPL
превышение над случайным входом +0.119R и минус после комиссий;
у фандинга поток +31% годовых и минус после ежедневной ротации.
Значит следующая работа не про индикаторы, а про цену доступа.

ВОПРОС. Если вместо «взять по рынку» поставить пассивную заявку
на лучшей цене — сколько это экономит ПОСЛЕ учёта двух неприятностей:
    неисполнение   заявка не налилась, приходится догонять дороже
    неблагоприятный отбор   наливают в основном тогда, когда цена
                            идёт против нас

МОДЕЛЬ ИСПОЛНЕНИЯ, консервативная и объявлена заранее.
Покупка. Ставим лимит на текущем лучшем биде P. Считаем заявку
исполненной, только если лучший бид ОПУСТИЛСЯ НИЖЕ P в течение
времени ожидания: значит очередь на этом уровне была выбита целиком,
и наша заявка (в конце очереди) тоже. Это заведомо занижает долю
исполнения — реальные частичные наливы не учитываются.

Если не налилось за время ожидания — догоняем по рынку.

СЧИТАЕМ ОДНО ЧИСЛО: эффективная цена входа относительно середины
на момент решения, в базисных пунктах, с комиссией. Ниже — лучше.

    тейкер сразу     (ask - mid)/mid + комиссия тейкера
    мейкер с догоном исполнено -> (bid - mid)/mid + комиссия мейкера
                     не исполнено -> (ask_потом - mid)/mid + комиссия тейкера

И отдельно — что цена делает ПОСЛЕ входа, чтобы увидеть
неблагоприятный отбор.
"""
from __future__ import annotations

import bisect
import json
import subprocess
import sys

import numpy as np

TAKER_BPS = 6.0
MAKER_BPS = 2.0
WAITS_S = (5, 15, 30, 60)
STEP_S = 60                 # решения не перекрываются
FWD_S = 300                 # что с ценой через 5 минут после входа


def open_any(fp):
    if fp.endswith(".zst"):
        return subprocess.Popen(["zstd", "-dc", fp], stdout=subprocess.PIPE, text=True).stdout
    return open(fp)


def book_series(fp):
    bids, asks = {}, {}
    valid = False
    ts_l, bb_l, ba_l, imb_l = [], [], [], []
    for line in open_any(fp):
        try:
            r = json.loads(line)
        except Exception:
            continue
        kind = r.get("kind")
        if kind == "gap":
            valid = False; continue
        pl = r.get("payload") or {}
        d = pl.get("data", pl)
        b_upd = d.get("b") or d.get("bids") or []
        a_upd = d.get("a") or d.get("asks") or []
        ts = r.get("local_recv_ts_ms") or 0
        if kind == "snapshot":
            bids = {float(p): float(s) for p, s in b_upd if float(s) > 0}
            asks = {float(p): float(s) for p, s in a_upd if float(s) > 0}
            valid = True
        elif kind == "delta":
            if not valid:
                continue
            for side, upd in ((bids, b_upd), (asks, a_upd)):
                for p, s in upd:
                    p, s = float(p), float(s)
                    if s <= 0: side.pop(p, None)
                    else: side[p] = s
        else:
            continue
        if not bids or not asks:
            continue
        bb, ba = max(bids), min(asks)
        if ba <= bb:
            continue
        bt = sorted(bids.items(), key=lambda kv: -kv[0])[:5]
        at = sorted(asks.items(), key=lambda kv: kv[0])[:5]
        bv, av = sum(v for _, v in bt), sum(v for _, v in at)
        ts_l.append(ts); bb_l.append(bb); ba_l.append(ba)
        imb_l.append((bv - av) / (bv + av) if bv + av > 0 else 0.0)
    return (np.array(ts_l), np.array(bb_l), np.array(ba_l), np.array(imb_l))


def run(fp, sym, day):
    ts, bb, ba, imb = book_series(fp)
    if len(ts) < 1000:
        return []
    mid = (bb + ba) / 2
    tl = ts.tolist()
    out = []
    t = ts[0]
    while t < ts[-1] - (max(WAITS_S) + FWD_S) * 1000:
        i = bisect.bisect_left(tl, t)
        t += STEP_S * 1000
        if i >= len(ts) - 5:
            break
        m0, p_lim, ask0 = mid[i], bb[i], ba[i]
        taker = (ask0 - m0) / m0 * 1e4 + TAKER_BPS
        row = dict(sym=sym, day=day, ts=int(ts[i]), imb=float(imb[i]),
                   spread=float((ba[i] - bb[i]) / m0 * 1e4), taker=float(taker))
        for W in WAITS_S:
            j = bisect.bisect_left(tl, ts[i] + W * 1000)
            j = min(j, len(ts) - 1)
            seg = bb[i + 1:j + 1]
            filled = bool(seg.size and seg.min() < p_lim)
            if filled:
                eff = (p_lim - m0) / m0 * 1e4 + MAKER_BPS
                entry = p_lim
            else:
                eff = (ba[j] - m0) / m0 * 1e4 + TAKER_BPS
                entry = ba[j]
            k = bisect.bisect_left(tl, ts[i] + (W + FWD_S) * 1000)
            k = min(k, len(ts) - 1)
            row[f"fill{W}"] = filled
            row[f"eff{W}"] = float(eff)
            row[f"fwd{W}"] = float((mid[k] / entry - 1) * 1e4)
            # ЧИСТЫЙ ИТОГ: обе руки меряются до ОДНОГО момента времени.
            # тейкер взял по ask сразу, мейкер — как получилось.
            row[f"net_mk{W}"] = float((mid[k] / entry - 1) * 1e4
                                      - (MAKER_BPS if filled else TAKER_BPS))
            row[f"net_tk{W}"] = float((mid[k] / ask0 - 1) * 1e4 - TAKER_BPS)
        out.append(row)
    print(f"{sym} {day}: решений {len(out):,}, медианный спред "
          f"{np.median([r['spread'] for r in out]):.3f} bps")
    return out


def main():
    rows = []
    for arg in sys.argv[1:]:
        fp, sym, day = arg.split(":")
        rows += run(fp, sym, day)
    if not rows:
        raise SystemExit("нет данных")
    days = sorted({r["day"] for r in rows})
    syms = sorted({r["sym"] for r in rows})

    for sym in syms:
        print(f"\n═══ {sym}   (ниже = дешевле; всё в bps от середины на момент решения)")
        print(f"{'ожидание':<10}{'налив':>8}{'мейкер+догон':>15}{'тейкер':>10}"
              f"{'экономия':>11}{'ход после входа':>18}")
        for W in WAITS_S:
            g = [r for r in rows if r["sym"] == sym]
            if len(g) < 100:
                continue
            fill = np.mean([r[f"fill{W}"] for r in g])
            eff = np.mean([r[f"eff{W}"] for r in g])
            tak = np.mean([r["taker"] for r in g])
            f_ok = [r[f"fwd{W}"] for r in g if r[f"fill{W}"]]
            f_no = [r[f"fwd{W}"] for r in g if not r[f"fill{W}"]]
            fwd = np.mean(f_ok) if f_ok else float("nan")
            print(f"{str(W)+' с':<10}{fill:>8.0%}{eff:>15.3f}{tak:>10.3f}"
                  f"{tak-eff:>+11.3f}{fwd:>18.2f}")
        if f_no:
            print(f"   для сравнения, ход после НЕисполнения: {np.mean(f_no):+.2f} bps")

    print("\n═══ ПРОВЕРКА НА ДРУГОМ ДНЕ (экономия, bps)")
    print(f"{'символ':<10}{'ожидание':<10}" + "".join(f"{d:>12}" for d in days))
    for sym in syms:
        for W in WAITS_S:
            cells = []
            for d in days:
                g = [r for r in rows if r["sym"] == sym and r["day"] == d]
                if len(g) < 50:
                    cells.append("   —"); continue
                cells.append(f"{np.mean([r['taker'] for r in g]) - np.mean([r[f'eff{W}'] for r in g]):+.3f}")
            print(f"{sym:<10}{str(W)+' с':<10}" + "".join(f"{c:>12}" for c in cells))

    print("\n═══ ПОМОГАЕТ ЛИ ДИСБАЛАНС ВЫБИРАТЬ МОМЕНТ (ожидание 30 с)")
    q = np.quantile([r["imb"] for r in rows], [1 / 3, 2 / 3])
    for k, lab in ((0, "книга давит вниз"), (1, "ровно"), (2, "книга давит вверх")):
        g = [r for r in rows if (0 if r["imb"] <= q[0] else 1 if r["imb"] <= q[1] else 2) == k]
        if len(g) < 100:
            continue
        fill = np.mean([r["fill30"] for r in g])
        sav = np.mean([r["taker"] for r in g]) - np.mean([r["eff30"] for r in g])
        fwd = np.mean([r["fwd30"] for r in g if r["fill30"]] or [np.nan])
        print(f"  {lab:<20} n={len(g):>5}  налив {fill:>4.0%}  "
              f"экономия {sav:+.3f} bps  ход после входа {fwd:+.2f} bps")

    print("\n═══ ЧИСТЫЙ ИТОГ СДЕЛКИ: вход + ход цены до одного и того же момента")
    print("    (условная покупка, удержание 5 минут после окончания ожидания)")
    print(f"{'символ':<10}{'ожидание':<10}{'мейкер':>10}{'тейкер':>10}{'разница':>11}{'n':>7}")
    res = {}
    for sym in syms:
        for W in WAITS_S:
            g = [r for r in rows if r["sym"] == sym]
            mk = np.mean([r[f"net_mk{W}"] for r in g])
            tk = np.mean([r[f"net_tk{W}"] for r in g])
            print(f"{sym:<10}{str(W)+' с':<10}{mk:>+10.3f}{tk:>+10.3f}{mk-tk:>+11.3f}{len(g):>7}")
            res[f"{sym}_{W}"] = dict(maker=float(mk), taker=float(tk), diff=float(mk - tk))
    print("\n    разница положительна -> лимитный вход выгоднее ПОСЛЕ учёта")
    print("    неблагоприятного отбора; отрицательна -> отбор съел экономию")
    json.dump(dict(n=len(rows), syms=syms, days=days, net=res),
              open("limit_entry.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
