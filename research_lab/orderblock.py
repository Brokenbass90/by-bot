#!/usr/bin/env python3
"""orderblock.py — ордерблоки на часах, 4h и днях, с ДВУМЯ контролями.

ПРАВИЛА ОБЪЯВЛЕНЫ ДО ПРОГОНА.

Что считаем ордерблоком (определение зафиксировано, не подбирается):
  1. Импульс: за DISP_BARS баров цена прошла >= DISP_ATR × ATR в одну
     сторону от закрытия свечи-кандидата.
  2. Ордерблок: последняя свеча ПРОТИВОПОЛОЖНОГО цвета перед этим
     импульсом. Для медвежьего импульса — последняя зелёная,
     для бычьего — последняя красная.
  3. Зона: диапазон тела этой свечи [min(o,c), max(o,c)].
  4. Вход: цена вернулась в зону в течение RETURN_MAX баров.
     Входим ПО НАПРАВЛЕНИЮ импульса, по открытию следующего бара.
  5. Стоп: за границей зоны, с запасом STOP_PAD × ATR.
  6. Цели: 1.2R (доля 0.55) и 2.5R — как у остальных наших ног.

Всё причинно: на баре i известны только бары до i включительно.

ДВА КОНТРОЛЯ, и второй важнее первого.

  Контроль А — случайный вход: та же монета, тот же месяц, та же
  геометрия, случайный момент. Отвечает на вопрос «а не рынок ли это».

  Контроль Б — «просто недавно торгованный уровень»: берём свечу
  из того же окна, за которой импульса НЕ БЫЛО, ждём возврата в её
  тело и входим в ту же сторону с той же геометрией. Отвечает
  на главный вопрос: **важен ли сам ордерблок или достаточно
  того, что цена вернулась к уровню, где недавно торговали.**

КРИТЕРИЙ, ОБЪЯВЛЕННЫЙ ЗАРАНЕЕ. Ордерблок принимается как кандидат,
только если ОДНОВРЕМЕННО на обоих окнах:
    итог выше контроля А (не рынок);
    итог выше контроля Б (важен именно ордерблок, а не уровень).
Превышение только над А — значит мы измерили «возврат к уровню»,
а не ордерблок, и записывать надо именно так.
"""
from __future__ import annotations
import argparse, glob, math, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research_lab/data/h1"
SEAL = 1759276800000
WINDOWS = {"2024-03..2025-09": (1709251200000, 1759276800000),
           "2023-01..2024-02": (1672531200000, 1709251200000)}
DISP_ATR, DISP_BARS = 2.0, 5      # импульс: 2 ATR за 5 баров
RETURN_MAX = 40                   # столько баров ждём возврата в зону
STOP_PAD = 0.5                    # запас за зоной, в ATR
RR1, RR2, F1 = 1.2, 2.5, 0.55
HOLD = 60                         # баров удержания
FEE_BPS_SIDE = 6.0
ATR_N = 14
DRAWS = 10


def agg(ts, o, k):
    """склейка часовых баров в бары по k часов"""
    if k == 1:
        return ts, o
    n = len(ts) // k * k
    ts, o = ts[:n], o[:n]
    ts2 = ts[::k]
    op = o[::k, 0]
    hi = o[:, 1].reshape(-1, k).max(1)
    lo = o[:, 2].reshape(-1, k).min(1)
    cl = o[k - 1::k, 3]
    vo = o[:, 4].reshape(-1, k).sum(1)
    return ts2, np.column_stack([op, hi, lo, cl, vo])


def atr_series(o, n=ATR_N):
    h, l, c = o[:, 1], o[:, 2], o[:, 3]
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.empty(len(tr)); s = tr[:n].mean()
    for i, v in enumerate(tr):
        s = (s * (n - 1) + v) / n; out[i] = s
    return out


def sim(o, e, short, zone_lo, zone_hi, atr, mult=1.0):
    """вход по открытию бара e, стоп за зоной, цели в единицах R"""
    if e >= len(o):
        return None
    entry = float(o[e, 0])
    sl0 = zone_hi + STOP_PAD * atr if short else zone_lo - STOP_PAD * atr
    sl = entry + (sl0 - entry) * mult
    risk = (sl - entry) if short else (entry - sl)
    if risk <= 0:
        return None
    lev = entry / risk
    cost = lev * 2 * FEE_BPS_SIDE / 1e4
    tp1 = entry - RR1 * risk if short else entry + RR1 * risk
    tp2 = entry - RR2 * risk if short else entry + RR2 * risk
    stop, rem, gross, done = sl, 1.0, 0.0, False
    for j in range(e, min(e + HOLD, len(o))):
        h, l = float(o[j, 1]), float(o[j, 2])
        if (h >= stop) if short else (l <= stop):
            return gross + rem * ((entry - stop) if short else (stop - entry)) / risk - cost
        if not done and ((l <= tp1) if short else (h >= tp1)):
            gross += F1 * RR1; rem -= F1; done = True
        if rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            return gross + rem * RR2 - cost
    j = min(e + HOLD, len(o)) - 1
    px = float(o[j, 3])
    return gross + rem * ((entry - px) if short else (px - entry)) / risk - cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", type=int, default=1, help="часов в баре: 1, 4 или 24")
    ap.add_argument("--symbols", type=int, default=137)
    ap.add_argument("--stopmult", type=float, default=1.0,
                    help="во сколько раз расширить стоп от зоны. Объявлено "
                         "заранее: 1 и 4. Узкий стоп у нас убивал всё, "
                         "поэтому широкий проверяется сразу, а не потом.")
    a = ap.parse_args()
    files = sorted(glob.glob(str(DATA / "*.npz")))[: a.symbols]
    rng = np.random.default_rng(23)
    real = {w: [] for w in WINDOWS}
    ctrlA = {w: [[] for _ in range(DRAWS)] for w in WINDOWS}
    ctrlB = {w: [[] for _ in range(DRAWS)] for w in WINDOWS}

    for k, fp in enumerate(files):
        d = np.load(fp); ts, o = d["ts"], d["ohlcv"].astype(float)
        m = ts < SEAL
        ts, o = ts[m], o[m]
        ts, o = agg(ts, o, a.tf)
        if len(ts) < 300:
            continue
        atr = atr_series(o)
        month = (ts // (30 * 86400000)).astype(np.int64)
        blocked = -1
        for i in range(ATR_N + DISP_BARS + 2, len(o) - 1):
            # ищем ордерблок, образовавшийся в прошлом, и возврат в него СЕЙЧАС
            for back in range(DISP_BARS + 1, min(RETURN_MAX, i - DISP_BARS - 2)):
                j = i - back                       # свеча-кандидат
                if atr[j] <= 0:
                    continue
                move = o[j + DISP_BARS, 3] - o[j, 3]
                if abs(move) < DISP_ATR * atr[j]:
                    continue
                short = move < 0
                # ордерблок = последняя свеча противоположного цвета
                ob = None
                for q in range(j, max(ATR_N, j - 6), -1):
                    up = o[q, 3] > o[q, 0]
                    if (up and short) or ((not up) and (not short)):
                        ob = q; break
                if ob is None:
                    continue
                zl, zh = min(o[ob, 0], o[ob, 3]), max(o[ob, 0], o[ob, 3])
                if zh <= zl:
                    continue
                # возврат в зону именно на баре i
                if not (o[i, 2] <= zh and o[i, 1] >= zl):
                    continue
                if i <= blocked:
                    break
                r = sim(o, i + 1, short, zl, zh, float(atr[i]), a.stopmult)
                if r is None:
                    break
                blocked = i + HOLD // 4
                for w, (wa, wb) in WINDOWS.items():
                    if wa <= ts[i] < wb:
                        real[w].append(r)
                        pool = np.flatnonzero((month == month[i]) &
                                              (np.arange(len(ts)) > ATR_N + DISP_BARS + 2) &
                                              (np.arange(len(ts)) < len(ts) - 1))
                        if len(pool) < 5:
                            break
                        for dr in range(DRAWS):
                            # контроль А: случайный момент, та же геометрия
                            p = int(rng.choice(pool))
                            w2 = (zh - zl)
                            c0 = float(o[p, 3])
                            x = sim(o, p + 1, short, c0 - w2 / 2, c0 + w2 / 2, float(atr[p]), a.stopmult)
                            if x is not None:
                                ctrlA[w][dr].append(x)
                            # контроль Б: свеча БЕЗ импульса, возврат в её тело
                            for _try in range(6):
                                q = int(rng.choice(pool))
                                if q + DISP_BARS >= len(o) or atr[q] <= 0:
                                    continue
                                mv = o[q + DISP_BARS, 3] - o[q, 3]
                                if abs(mv) >= DISP_ATR * atr[q]:
                                    continue          # это импульс, не подходит
                                bl, bh = min(o[q, 0], o[q, 3]), max(o[q, 0], o[q, 3])
                                if bh <= bl:
                                    continue
                                # ждём возврата в тело
                                hit = None
                                for z in range(q + DISP_BARS + 1,
                                               min(q + DISP_BARS + 1 + RETURN_MAX, len(o) - 1)):
                                    if o[z, 2] <= bh and o[z, 1] >= bl:
                                        hit = z; break
                                if hit is None:
                                    continue
                                y = sim(o, hit + 1, short, bl, bh, float(atr[hit]), a.stopmult)
                                if y is not None:
                                    ctrlB[w][dr].append(y)
                                break
                break
        if (k + 1) % 40 == 0:
            print(f"... {k+1}/{len(files)}", flush=True)

    print(f"\nОРДЕРБЛОКИ, бар = {a.tf} ч, стоп ×{a.stopmult}, импульс {DISP_ATR} ATR за {DISP_BARS} баров")
    print(f"{'окно':<20}{'n':>6}{'ордерблок':>12}{'А: случайно':>13}"
          f"{'Б: просто уровень':>19}{'над А':>10}{'над Б':>10}{'вердикт':>14}")
    for w in WINDOWS:
        R = np.array(real[w])
        A = np.array([np.mean(x) for x in ctrlA[w] if len(x) > 15])
        B = np.array([np.mean(x) for x in ctrlB[w] if len(x) > 15])
        if len(R) < 50 or len(A) < 3 or len(B) < 3:
            print(f"{w:<20}{len(R):>6}  сделок мало"); continue
        dA, dB = R.mean() - A.mean(), R.mean() - B.mean()
        v = "кандидат" if (dA > 0 and dB > 0) else ("только уровень" if dA > 0 else "нет")
        print(f"{w:<20}{len(R):>6}{R.mean():>+11.4f}R{A.mean():>+12.4f}R"
              f"{B.mean():>+18.4f}R{dA:>+9.4f}R{dB:>+9.4f}R{v:>14}")


if __name__ == "__main__":
    main()
