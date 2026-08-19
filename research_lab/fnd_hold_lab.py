#!/usr/bin/env python3
"""Диагностика частоты для фандинг-ноги: где перевод перестаёт съедаться комиссией.

НЕ РЕЗУЛЬТАТ. Ежедневная версия объявлена мёртвой по своим критериям.
Здесь считается арифметика оборота: фандинг капает непрерывно, а платим
мы только когда меняется состав книги. Значит держать дольше — это не
подгонка под доходность, а прямое следствие структуры издержек.

Издержки считаются по ФАКТИЧЕСКОМУ обороту: платим только за имена,
которые вошли или вышли, а не за всю книгу каждый раз.
"""
import bisect, glob, json, os
import numpy as np

CUTOFF_MS = 1759190400000
DAY_MS = 86_400_000
K = 5
LOOKBACK = 3
MIN_AGE = 90
MIN_TURN = 5e6
FUND_DIR = "fnd/bybit_public_archive_2023/funding"
BAR_DIR = "fnd/bybit_daily_preholdout_2023_20250930/bars"

bars, fund = {}, {}
for fp in sorted(glob.glob(os.path.join(BAR_DIR, "*.json"))):
    s = os.path.basename(fp)[:-5]
    r = [x for x in json.load(open(fp))["records"] if x["ts_ms"] < CUTOFF_MS]
    if len(r) < MIN_AGE + 30: continue
    bars[s] = dict(ts=np.array([x["ts_ms"] for x in r]),
                   o=np.array([x["open"] for x in r], float),
                   turn=np.array([x["turnover"] for x in r], float))
for fp in sorted(glob.glob(os.path.join(FUND_DIR, "*.json"))):
    s = os.path.basename(fp)[:-5]
    if s not in bars: continue
    r = [x for x in json.load(open(fp))["records"] if x["funding_time_ms"] < CUTOFF_MS]
    if len(r) < 100: bars.pop(s, None); continue
    fund[s] = (np.array([x["funding_time_ms"] for x in r]),
               np.array([x["funding_rate"] for x in r], float))
syms = sorted(fund)
days = np.unique(np.concatenate([bars[s]["ts"] for s in syms]))
days = days[days < CUTOFF_MS - 20 * DAY_MS]

def rank_day(t):
    cand = []
    for s in syms:
        b = bars[s]; i = int(np.searchsorted(b["ts"], t))
        if i >= len(b["ts"]) - 2 or b["ts"][i] != t or i < MIN_AGE: continue
        if b["turn"][i] < MIN_TURN: continue
        ft, fr = fund[s]
        j = int(np.searchsorted(ft, t + DAY_MS))
        if j < LOOKBACK: continue
        cand.append((float(fr[j - LOOKBACK:j].mean()), s, i))
    cand.sort()
    return cand

def run(hold, cost_bps=15.0):
    """Возвращает: фандинг, цена, оборот, чистый — в процентах за сутки."""
    prev = set()
    fnd_t = px_t = cost_t = 0.0
    ndays = 0
    for d0 in range(0, len(days) - hold - 2, hold):
        t = days[d0]
        cand = rank_day(t)
        if len(cand) < 4 * K: continue
        book = {}
        for _, s, i in cand[:K]: book[s] = (+1, i)
        for _, s, i in cand[-K:]: book[s] = (-1, i)
        ok = True
        f_sum = p_sum = 0.0
        for s, (side, i) in book.items():
            b = bars[s]; e_i, x_i = i + 1, i + 1 + hold
            if x_i >= len(b["o"]): ok = False; break
            e, x = b["o"][e_i], b["o"][x_i]
            p_sum += side * (x / e - 1) / K
            ft, fr = fund[s]
            a = bisect.bisect_right(ft.tolist(), int(b["ts"][e_i]))
            z = bisect.bisect_right(ft.tolist(), int(b["ts"][x_i]))
            f_sum += -side * float(fr[a:z].sum()) / K
        if not ok: continue
        cur = set(book)
        churn = len(cur ^ prev) / (2 * K)          # доля книги, которая реально торгуется
        prev = cur
        fnd_t += f_sum; px_t += p_sum
        cost_t += churn * cost_bps / 1e4
        ndays += hold
    if ndays == 0: return None
    return (fnd_t / ndays * 100, px_t / ndays * 100, cost_t / ndays * 100,
            (fnd_t + px_t - cost_t) / ndays * 100, ndays)

print("держим H суток; всё в процентах капитала ЗА СУТКИ; издержки по факту оборота\n")
print(f"{'H':>4}{'фандинг':>11}{'цена':>10}{'издержки':>11}{'чистыми':>11}{'в год':>10}")
best = None
for hold in (1, 2, 3, 5, 7, 10, 14, 21):
    r = run(hold)
    if not r: continue
    f, p, c, n, nd = r
    print(f"{hold:>4}{f:>+11.5f}{p:>+10.5f}{c:>11.5f}{n:>+11.5f}{n*365:>+10.1f}%")
    if best is None or n > best[0]: best = (n, hold)
print(f"\nлучший по чистой доходности: H={best[1]} суток, {best[0]*365:+.1f}% годовых")
print("\nтот же расчёт при удвоенных издержках (30 bps):")
print(f"{'H':>4}{'чистыми':>11}{'в год':>10}")
for hold in (3, 7, 14, 21):
    r = run(hold, 30.0)
    if r: print(f"{hold:>4}{r[3]:>+11.5f}{r[3]*365:>+10.1f}%")
