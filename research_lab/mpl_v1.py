#!/usr/bin/env python3
"""
mpl_v1.py — Momentum Pullback to Level, версия 1.

ЧТО ЭТО. Идея владельца в её исходном виде, до того как её переделали
в пробойную: монета, в которую заходят деньги, уже пошла вверх; мы
входим НЕ на импульсе и НЕ на пробое, а на откате; целью ставим ближайший
сильный уровень сверху; и выходим ДО него, потому что на самом уровне
начинается другая игра.

ПРАВИЛА ОБЪЯВЛЕНЫ ДО ПРОГОНА И НЕ ПОДБИРАЮТСЯ.

  ОТБОР МОНЕТЫ (деньги заходят)
      объём за 24 ч >= 1.5 медианного суточного объёма за 30 дней
      доходность за 24 ч в верхних 20% по срезу всех монет этого часа

  ИМПУЛЬС
      максимум последних 24 ч поставлен не раньше 6 часов назад
      высота импульса (от минимума за 24 ч до этого максимума) >= 2 ATR24

  УРОВЕНЬ (цель)
      максимум за 30 дней, посчитанный по данным, которые старше
      импульса на сутки — чтобы уровень не был нарисован самим импульсом
      требуется 1.0 ATR24 <= (уровень - цена) <= 6 ATR24

  ОТКАТ И ВХОД
      цена откатила от импульсного максимума на 30-60% его высоты
      вход по закрытию первого часа, который закрылся выше максимума
      предыдущего часа, но не позже 12 часов после импульсного максимума

  СТОП   минимум отката минус 0.25 ATR24
  ЦЕЛЬ   уровень минус 0.3 ATR24   <-- в этом вся идея
  ВРЕМЯ  48 часов, потом выход по рынку
  ИЗДЕРЖКИ 16 bps круг

ТРИ РУКИ, чтобы проверить ИМЕННО утверждение владельца:
  A  выход до уровня        (уровень - 0.3 ATR)
  B  выход за уровнем       (уровень + 0.3 ATR)   — насквозь
  C  случайный вход в тех же монетах и часах, тот же стоп и цель

КРИТЕРИЙ СМЕРТИ, объявлен сейчас:
  рука A умирает, если средний R после издержек <= 0 на контрольной
  половине символов, ИЛИ если превышение над рукой C меньше 0.05R,
  ИЛИ если положительных хронологических фолдов меньше 3 из 4.
  Утверждение «выходить до уровня лучше» считается подтверждённым
  только если A - B > 0 и нижняя граница разницы по недельному
  блочному бутстрапу выше нуля.

Запечатанный холдаут 2025-10..2026-06 не читается: все данные
обрезаются по 2025-09-30.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

DIR = sys.argv[1] if len(sys.argv) > 1 else "h1/h1"
CUTOFF_MS = 1759190400000          # 2025-09-30 00:00 UTC
COST_BPS = 16.0
ATR_N = 24
VOL_MULT = 1.5
TOP_FRAC = 0.20
IMP_MIN_ATR = 2.0
IMP_MAX_AGE = 6
PB_LO, PB_HI = 0.30, 0.60
MAX_WAIT = 12
STOP_BUF = 0.25
TGT_BUF = 0.30
LVL_LOOKBACK = 720                 # 30 дней в часах
LVL_GAP = 24                       # уровень строим по данным старше суток
MIN_ROOM, MAX_ROOM = 1.0, 6.0
HOLD_H = 48


def atr(h, l, c, n=ATR_N):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(tr), np.nan)
    if len(tr) > n:
        k = np.convolve(tr, np.ones(n) / n, mode="full")[: len(tr)]
        out[n:] = k[n:]
    return out


def rolling_max(a, n):
    out = np.full(len(a), np.nan)
    for i in range(n, len(a)):
        out[i] = a[i - n:i].max()
    return out


def rolling_min(a, n):
    out = np.full(len(a), np.nan)
    for i in range(n, len(a)):
        out[i] = a[i - n:i].min()
    return out


def load():
    data = {}
    for fp in sorted(glob.glob(os.path.join(DIR, "*.npz"))):
        sym = os.path.basename(fp)[:-4]
        d = np.load(fp)
        ts, o = d["ts"], d["ohlcv"].astype(np.float64)
        m = ts <= CUTOFF_MS
        if m.sum() < LVL_LOOKBACK + 200:
            continue
        data[sym] = dict(ts=ts[m], o=o[m, 0], h=o[m, 1], l=o[m, 2],
                         c=o[m, 3], v=o[m, 4])
    return data


def prepare(d):
    h, l, c, v = d["h"], d["l"], d["c"], d["v"]
    d["atr"] = atr(h, l, c)
    d["hi24"] = rolling_max(h, 24)
    d["lo24"] = rolling_min(l, 24)
    # уровень: максимум за 30 дней по данным, которые кончаются сутки назад
    lvl = np.full(len(h), np.nan)
    for i in range(LVL_LOOKBACK + LVL_GAP, len(h)):
        lvl[i] = h[i - LVL_LOOKBACK - LVL_GAP:i - LVL_GAP].max()
    d["lvl"] = lvl
    # объём: сумма за 24 ч против медианы суточного объёма за 30 дней
    cv = np.convolve(v, np.ones(24), mode="full")[: len(v)]
    v24 = np.full(len(v), np.nan)
    v24[24:] = cv[24:]
    med = np.full(len(v), np.nan)
    for i in range(LVL_LOOKBACK, len(v), 1):
        med[i] = np.median(v24[i - LVL_LOOKBACK:i])
    d["vratio"] = v24 / med
    d["ret24"] = np.concatenate([[np.nan] * 24, c[24:] / c[:-24] - 1])
    return d


def cross_rank(data, syms):
    """Ранг доходности за 24 ч по срезу всех монет в каждый час."""
    all_ts = np.unique(np.concatenate([data[s]["ts"] for s in syms]))
    pos = {t: i for i, t in enumerate(all_ts)}
    M = np.full((len(all_ts), len(syms)), np.nan)
    for j, s in enumerate(syms):
        idx = np.array([pos[t] for t in data[s]["ts"]])
        M[idx, j] = data[s]["ret24"]
    rk = np.full(M.shape, np.nan)
    for i in range(M.shape[0]):
        row = M[i]
        ok = np.isfinite(row)
        if ok.sum() >= 20:
            r = np.argsort(np.argsort(row[ok])) / (ok.sum() - 1)
            rk[i, ok] = r
    for j, s in enumerate(syms):
        idx = np.array([pos[t] for t in data[s]["ts"]])
        data[s]["rank"] = rk[idx, j]
    return data


def signals(d, sym):
    """Возвращает список сигналов: (ts, i_entry, entry, stop, level, atr)."""
    h, l, c = d["h"], d["l"], d["c"]
    a, hi24, lo24, lvl = d["atr"], d["hi24"], d["lo24"], d["lvl"]
    out = []
    n = len(c)
    i = LVL_LOOKBACK + LVL_GAP + 30
    while i < n - HOLD_H - 1:
        if not (np.isfinite(a[i]) and a[i] > 0 and np.isfinite(lvl[i])
                and np.isfinite(d["vratio"][i]) and np.isfinite(d["rank"][i])):
            i += 1
            continue
        if d["vratio"][i] < VOL_MULT or d["rank"][i] < 1 - TOP_FRAC:
            i += 1
            continue
        # импульс: где стоит максимум последних 24 часов
        w = h[i - 24:i]
        k = int(np.argmax(w))
        age = 24 - k                     # сколько часов назад поставлен максимум
        imp_hi = w[k]
        imp_lo = l[i - 24:i - 24 + k + 1].min() if k >= 0 else np.nan
        if age > IMP_MAX_AGE or age < 1:
            i += 1
            continue
        height = imp_hi - imp_lo
        if not np.isfinite(height) or height < IMP_MIN_ATR * a[i]:
            i += 1
            continue
        room = lvl[i] - c[i]
        if not (MIN_ROOM * a[i] <= room <= MAX_ROOM * a[i]):
            i += 1
            continue
        # откат: насколько цена вернулась от импульсного максимума
        pb_lo_price = imp_hi - PB_HI * height
        pb_hi_price = imp_hi - PB_LO * height
        seg_lo = l[i - age:i + 1].min()
        if not (pb_lo_price <= seg_lo <= pb_hi_price):
            i += 1
            continue
        # вход: час закрылся выше максимума предыдущего часа
        if not (c[i] > h[i - 1]):
            i += 1
            continue
        entry = c[i]
        stop = seg_lo - STOP_BUF * a[i]
        if entry <= stop:
            i += 1
            continue
        out.append((int(d["ts"][i]), i, entry, stop, float(lvl[i]), float(a[i])))
        i += HOLD_H                      # не перекрываем сделки внутри символа
    return out


def simulate(d, sig, tgt_buf, hold=HOLD_H):
    """Бар за баром: что сработало раньше — стоп или цель."""
    h, l = d["h"], d["l"]
    res = []
    for ts, i, entry, stop, lvl, a in sig:
        tgt = lvl - tgt_buf * a
        risk = entry - stop
        if risk <= 0 or tgt <= entry:
            continue
        exitp, why = None, "time"
        for j in range(i + 1, min(i + 1 + hold, len(h))):
            if l[j] <= stop:
                exitp, why = stop, "stop"
                break
            if h[j] >= tgt:
                exitp, why = tgt, "target"
                break
        if exitp is None:
            exitp = d["c"][min(i + hold, len(h) - 1)]
        cost = entry * COST_BPS / 1e4
        R = (exitp - entry - cost) / risk
        res.append(dict(ts=ts, R=float(R), why=why, risk_bps=risk / entry * 1e4))
    return res


def week_boot(rs, tss, n=3000, seed=5):
    if len(rs) < 20:
        return float("nan"), float("nan")
    wk = (np.array(tss) // (7 * 86400_000)).astype(np.int64)
    ub = np.unique(wk)
    idx = {b: np.flatnonzero(wk == b) for b in ub}
    rng = np.random.default_rng(seed)
    r = np.array(rs)
    ms = np.empty(n)
    for i in range(n):
        pick = rng.choice(ub, len(ub), replace=True)
        ms[i] = r[np.concatenate([idx[b] for b in pick])].mean()
    return float(np.quantile(ms, 0.025)), float(np.quantile(ms, 0.975))


def report(name, res):
    if not res:
        print(f"{name:<26} сделок 0")
        return None
    R = np.array([r["R"] for r in res])
    ts = [r["ts"] for r in res]
    lo, hi = week_boot(R, ts)
    wr = float((R > 0).mean())
    tg = float(np.mean([r["why"] == "target" for r in res]))
    print(f"{name:<26} сделок {len(R):>5}  R/сделку {R.mean():+.4f}  "
          f"[{lo:+.3f} .. {hi:+.3f}]  винрейт {wr:.1%}  дошло до цели {tg:.1%}")
    return dict(n=len(R), mean=float(R.mean()), lo=lo, hi=hi, wr=wr, tgt=tg)


def main():
    data = load()
    syms = sorted(data)
    print(f"символов {len(syms)}, часовые бары до 2025-09-30\n")
    for s in syms:
        prepare(data[s])
    cross_rank(data, syms)

    allsig = {s: signals(data[s], s) for s in syms}
    tot = sum(len(v) for v in allsig.values())
    print(f"сигналов всего {tot:,} на {sum(1 for v in allsig.values() if v)} символах\n")
    if tot < 100:
        print("сигналов слишком мало — правила слишком узкие, это тоже ответ")
        return

    armA, armB, armC = [], [], []
    rng = np.random.default_rng(3)
    for s in syms:
        sig = allsig[s]
        if not sig:
            continue
        armA += simulate(data[s], sig, TGT_BUF)
        armB += simulate(data[s], sig, -TGT_BUF)
        # контроль: те же символы и то же число входов, но час случайный
        n = len(data[s]["c"])
        fake = []
        for ts, i, e, st, lvl, a in sig:
            j = int(rng.integers(LVL_LOOKBACK + LVL_GAP + 30, n - HOLD_H - 1))
            if not (np.isfinite(data[s]["atr"][j]) and np.isfinite(data[s]["lvl"][j])):
                continue
            aj = data[s]["atr"][j]
            fake.append((int(data[s]["ts"][j]), j, data[s]["c"][j],
                         data[s]["c"][j] - (e - st) / e * data[s]["c"][j],
                         data[s]["c"][j] + (lvl - e), aj))
        armC += simulate(data[s], fake, TGT_BUF)

    print("ВСЁ ЦЕЛИКОМ")
    A = report("A: выход ДО уровня", armA)
    B = report("B: выход ЗА уровнем", armB)
    C = report("C: случайный вход", armC)

    print("\nПО ПОЛОВИНАМ СИМВОЛОВ (вторая половина не участвовала в правилах)")
    half = set(syms[::2])
    for tag, keep in (("символы 1", True), ("символы 2", False)):
        sub = []
        for s in syms:
            if (s in half) == keep and allsig[s]:
                sub += simulate(data[s], allsig[s], TGT_BUF)
        report(f"A / {tag}", sub)

    print("\nПО ГОДАМ")
    yr = {}
    for r in armA:
        y = 1970 + r["ts"] // (365.25 * 86400_000)
        yr.setdefault(int(y), []).append(r)
    for y in sorted(yr):
        report(f"A / {y}", yr[y])

    if A and B:
        d = A["mean"] - B["mean"]
        print(f"\nГЛАВНАЯ ПРОВЕРКА ИДЕИ: выход до уровня минус выход за уровнем "
              f"= {d:+.4f} R")
    json.dump(dict(A=A, B=B, C=C, n_signals=tot),
              open("mpl_v1_result.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
