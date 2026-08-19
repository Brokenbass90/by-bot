#!/usr/bin/env python3
"""
fnd_v1.py — фандинг-ротация: денежный поток вместо прогноза цены.

ЗАЧЕМ ИМЕННО ЭТО СЕЙЧАС. Главный вывод проекта: направленную ставку
на нашей истории доказать нельзя, нейтральную — можно. XSEC отклонён,
но это был прогноз ОТНОСИТЕЛЬНОЙ ЦЕНЫ. Здесь источник дохода другой:
биржа физически переводит деньги от одной стороны к другой каждые
8 часов. Мы не угадываем движение, мы становимся получателем перевода.

ПРАВИЛО, объявлено ДО прогона:
    ранг       по среднему фандингу за последние 24 часа (3 выплаты)
    шорт       K символов с самым ВЫСОКИМ фандингом (лонги платят нам)
    лонг       K символов с самым НИЗКИМ (шорты платят нам)
    вес        равный по долларам, книга нейтральна по доллару
    решение    по закрытию дня i
    исполнение по ОТКРЫТИЮ дня i+1   <- вход исполнимый, не по тому же close
    выход      по открытию дня i+2 (удержание сутки)
    фандинг    суммируются все выплаты, попавшие в (вход, выход],
               денежный поток = -вес * ставка
    издержки   base 15 bps и stress 30 bps за полный ребаланс
    фильтр     символ должен торговаться не меньше 90 дней до решения
               и иметь суточный оборот не ниже $5 млн

ГЛАВНЫЙ ВОПРОС, ради которого всё считается раздельно:
фандинг это доход или ловушка. Высокая ставка означает, что рынок
перегружен лонгами. Возможны два исхода:
    а) мы получаем перевод, цена стоит  -> доход
    б) мы получаем перевод, но цена идёт против нас на ту же величину
       -> ноль или минус, а «доход» был иллюзией
Поэтому вклад цены и вклад фандинга печатаются ОТДЕЛЬНО. Если общий
результат положителен только за счёт цены — это не фандинг-нога,
а моментум, и она закрывается.

КРИТЕРИЙ СМЕРТИ, объявлен заранее:
  * итог после base издержек <= 0
  * или вклад фандинга сам по себе меньше издержек
  * или нижняя граница 95% недельного бутстрапа ниже нуля
Данные обрезаны 2025-10-01, запечатанный период не читается.
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys

import numpy as np

FUND_DIR = sys.argv[1] if len(sys.argv) > 1 else "fnd/bybit_public_archive_2023/funding"
BAR_DIR = sys.argv[2] if len(sys.argv) > 2 else "fnd/bybit_daily_preholdout_2023_20250930/bars"
CUTOFF_MS = 1759190400000              # 2025-10-01, дальше не смотрим
DAY_MS = 86_400_000
K = 5
LOOKBACK_PAYMENTS = 3                  # 24 часа
MIN_AGE_DAYS = 90
MIN_TURNOVER = 5e6
COST_SCENARIOS = (("base_15bps", 15.0), ("stress_30bps", 30.0))


def load():
    bars, fund = {}, {}
    for fp in sorted(glob.glob(os.path.join(BAR_DIR, "*.json"))):
        s = os.path.basename(fp)[:-5]
        r = json.load(open(fp))["records"]
        r = [x for x in r if x["ts_ms"] < CUTOFF_MS]
        if len(r) < MIN_AGE_DAYS + 30:
            continue
        bars[s] = dict(ts=np.array([x["ts_ms"] for x in r]),
                       o=np.array([x["open"] for x in r], float),
                       c=np.array([x["close"] for x in r], float),
                       turn=np.array([x["turnover"] for x in r], float))
    for fp in sorted(glob.glob(os.path.join(FUND_DIR, "*.json"))):
        s = os.path.basename(fp)[:-5]
        if s not in bars:
            continue
        r = [x for x in json.load(open(fp))["records"] if x["funding_time_ms"] < CUTOFF_MS]
        if len(r) < 100:
            bars.pop(s, None); continue
        fund[s] = (np.array([x["funding_time_ms"] for x in r]),
                   np.array([x["funding_rate"] for x in r], float))
    return {s: bars[s] for s in fund}, fund


def main():
    bars, fund = load()
    syms = sorted(bars)
    print(f"символов с барами и фандингом: {len(syms)}")
    all_days = np.unique(np.concatenate([bars[s]["ts"] for s in syms]))
    all_days = all_days[all_days < CUTOFF_MS - 3 * DAY_MS]
    print(f"дней: {len(all_days)}  "
          f"({np.datetime64(int(all_days[0]), 'ms')} .. {np.datetime64(int(all_days[-1]), 'ms')})\n")

    rng = np.random.default_rng(3)
    rows = []
    for t in all_days:
        cand = []
        for s in syms:
            b = bars[s]
            i = int(np.searchsorted(b["ts"], t))
            if i >= len(b["ts"]) - 2 or b["ts"][i] != t or i < MIN_AGE_DAYS:
                continue
            if b["turn"][i] < MIN_TURNOVER:
                continue
            ft, fr = fund[s]
            j = int(np.searchsorted(ft, t + DAY_MS))       # выплаты строго до решения
            if j < LOOKBACK_PAYMENTS:
                continue
            score = float(fr[j - LOOKBACK_PAYMENTS:j].mean())
            cand.append((score, s, i))
        if len(cand) < 4 * K:
            continue
        cand.sort()
        longs = cand[:K]            # самый низкий фандинг -> лонг
        shorts = cand[-K:]          # самый высокий -> шорт
        pick = rng.choice(len(cand), 2 * K, replace=False)
        r_long = [cand[x] for x in pick[:K]]
        r_short = [cand[x] for x in pick[K:]]

        def leg(sel, side):
            px_pnl = fnd_pnl = 0.0
            for _, s, i in sel:
                b = bars[s]
                e_i, x_i = i + 1, i + 2                    # вход и выход по ОТКРЫТИЮ
                if x_i >= len(b["o"]):
                    return None
                e, x = b["o"][e_i], b["o"][x_i]
                px_pnl += side * (x / e - 1) / K
                ft, fr = fund[s]
                a = bisect.bisect_right(ft.tolist(), int(b["ts"][e_i]))
                z = bisect.bisect_right(ft.tolist(), int(b["ts"][x_i]))
                fnd_pnl += -side * float(fr[a:z].sum()) / K
            return px_pnl, fnd_pnl

        real = [leg(longs, +1), leg(shorts, -1)]
        ctrl = [leg(r_long, +1), leg(r_short, -1)]
        if any(x is None for x in real + ctrl):
            continue
        rows.append(dict(ts=int(t),
                         px=real[0][0] + real[1][0], fnd=real[0][1] + real[1][1],
                         c_px=ctrl[0][0] + ctrl[1][0], c_fnd=ctrl[0][1] + ctrl[1][1]))

    if len(rows) < 100:
        print("дней с полным составом слишком мало"); return
    px = np.array([r["px"] for r in rows]); fn = np.array([r["fnd"] for r in rows])
    cpx = np.array([r["c_px"] for r in rows]); cfn = np.array([r["c_fnd"] for r in rows])
    ts = np.array([r["ts"] for r in rows])

    def boot(x, n=3000, seed=5):
        wk = ts // (7 * DAY_MS)
        ub = np.unique(wk); idx = {b: np.flatnonzero(wk == b) for b in ub}
        g = np.random.default_rng(seed); out = np.empty(n)
        for i in range(n):
            p = g.choice(ub, len(ub), replace=True)
            out[i] = x[np.concatenate([idx[b] for b in p])].mean()
        return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))

    print(f"ребалансов: {len(rows)}   K={K} на сторону, книга нейтральна по доллару\n")
    print("ВКЛАД ПО ИСТОЧНИКАМ, в процентах капитала за сутки (до издержек)")
    print(f"  фандинг      {fn.mean()*100:+.5f}%   за год ~{fn.mean()*365*100:+.1f}%")
    print(f"  цена         {px.mean()*100:+.5f}%   за год ~{px.mean()*365*100:+.1f}%")
    print(f"  вместе       {(fn+px).mean()*100:+.5f}%")
    print(f"  контроль (случайные символы): фандинг {cfn.mean()*100:+.5f}%  "
          f"цена {cpx.mean()*100:+.5f}%\n")

    for name, bps in COST_SCENARIOS:
        cost = bps / 1e4
        net = fn + px - cost
        lo, hi = boot(net)
        ann = net.mean() * 365 * 100
        sh = net.mean() / net.std() * np.sqrt(365) if net.std() > 0 else float("nan")
        print(f"{name:<14} за сутки {net.mean()*100:+.5f}%  за год {ann:+.1f}%  "
              f"Sharpe {sh:+.2f}  интервал [{lo*100:+.4f}..{hi*100:+.4f}]%")

    base_net = fn + px - COST_SCENARIOS[0][1] / 1e4
    lo0, _ = boot(base_net)
    dead = []
    if base_net.mean() <= 0:
        dead.append("итог после base издержек <= 0")
    if fn.mean() <= COST_SCENARIOS[0][1] / 1e4:
        dead.append("фандинг сам по себе меньше издержек")
    if lo0 <= 0:
        dead.append("нижняя граница бутстрапа ниже нуля")
    print("\nКРИТЕРИИ СМЕРТИ (объявлены до прогона):")
    for name in ("итог после base издержек <= 0", "фандинг сам по себе меньше издержек",
                 "нижняя граница бутстрапа ниже нуля"):
        print(f"  {name:<44} {'ДА' if name in dead else 'нет'}")
    print(f"\nВЕРДИКТ: {'МЕРТВА' if dead else 'ЖИВА, идёт дальше на проверку'}")
    json.dump(dict(n=len(rows), funding=float(fn.mean()), price=float(px.mean()),
                   ctrl_funding=float(cfn.mean()), ctrl_price=float(cpx.mean()),
                   base_net=float(base_net.mean()), lo=lo0, dead=dead),
              open("fnd_v1_result.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
