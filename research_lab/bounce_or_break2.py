#!/usr/bin/env python3
"""
bounce_or_break.py — ДЕТЕКТОР: уровень удержит или пробьют.

ЗАЧЕМ ЭТО, А НЕ ОЧЕРЕДНАЯ НОГА. Главный урок этих исследований: мощность
даёт ШИРОТА. Одна нога на одном символе — это несколько сотен сделок, и
на них нельзя отличить эдж от шума. Детектор строится по ВСЕМ символам
сразу, и событий там десятки тысяч. Плюс он нужен не одной ноге, а всей
библиотеке: отскоки, пробои, ретесты, флэт — всё это про уровни.

СОБЫТИЕ. Цена подошла к уровню (экстремум прошлой недели) ближе чем
на 0.5 ATR, но ещё не закрылась за ним.

ИСХОД — гонка барьеров, без произвола:
    ПРОБОЙ   цена первой достигла уровень + 1.0 ATR
    ОТСКОК   цена первой ушла на 2.0 ATR в сторону от уровня
    иначе    исход не определён за 24 часа, событие выбрасывается

ПРИЗНАКИ на момент подхода, все только по прошлому:
    touches      сколько раз цена подходила к уровню за прошлую неделю
    age          сколько часов назад уровень был установлен
    approach     скорость подхода: ход за 12ч в ATR
    vol_rel      объём 6ч к медиане суток
    atr_rel      ATR к своей недельной медиане
    dist_ma      расстояние до недельной средней в ATR
    btc          состояние битка: рост / вбок / падение

ПРОВЕРКА. Данные делятся дважды и независимо:
    по ВРЕМЕНИ    ранняя половина учит, поздняя проверяет
    по СИМВОЛАМ   половина монет учит, другая проверяет
Признак принимается, только если работает в ОБОИХ проверках. Это защита
от подгонки, которую не даёт одиночное разделение.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

H1 = sys.argv[1] if len(sys.argv) > 1 else "research_lab/data/h1"
OUT = sys.argv[2] if len(sys.argv) > 2 else "research_lab/results/bounce_break"
WEEK = 168
NEAR = 0.5        # «подошла» = ближе этого в ATR
BREAK_B = 1.0     # барьер пробоя, в ATR за уровнем
BOUNCE_B = 2.0    # барьер отскока, в ATR от уровня
HOR = 24          # часов на разрешение исхода
MIN_GAP = 12      # дедуп событий на символ, часов


def load(h1dir):
    out = {}
    for fp in sorted(glob.glob(os.path.join(h1dir, "*.npz"))):
        z = np.load(fp)
        idx = pd.to_datetime(z["ts"], unit="ms", utc=True)
        d = pd.DataFrame(z["ohlcv"][:, :5].astype("float64"),
                         index=idx, columns=list("ohlcv"))
        if len(d) >= WEEK * 4:
            out[os.path.basename(fp)[:-4]] = d[~d.index.duplicated()]
    return out


def events_for(sym, d, btc_state):
    c, h, l, v = d["c"].to_numpy(), d["h"].to_numpy(), d["l"].to_numpy(), d["v"].to_numpy()
    n = len(c)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    atr = pd.Series(tr).ewm(alpha=1 / 24, adjust=False, min_periods=24).mean().to_numpy()
    hi = pd.Series(h).shift(1).rolling(WEEK, min_periods=WEEK).max().to_numpy()
    lo = pd.Series(l).shift(1).rolling(WEEK, min_periods=WEEK).min().to_numpy()
    sma = pd.Series(c).rolling(WEEK, min_periods=WEEK).mean().to_numpy()
    # СОВПАДЕНИЕ ТАЙМФРЕЙМОВ: тот же экстремум на месяце и на квартале.
    # Уровень, который одновременно недельный и месячный, — другой объект,
    # и это никогда не проверялось.
    MON, QTR = WEEK * 4, WEEK * 13
    hi_m = pd.Series(h).shift(1).rolling(MON, min_periods=MON).max().to_numpy()
    lo_m = pd.Series(l).shift(1).rolling(MON, min_periods=MON).min().to_numpy()
    hi_q = pd.Series(h).shift(1).rolling(QTR, min_periods=QTR).max().to_numpy()
    lo_q = pd.Series(l).shift(1).rolling(QTR, min_periods=QTR).min().to_numpy()
    v6 = pd.Series(v).rolling(6, min_periods=3).sum().to_numpy()
    vmed = pd.Series(v).rolling(24, min_periods=12).median().to_numpy() * 6
    amed = pd.Series(atr).rolling(WEEK, min_periods=24).median().to_numpy()
    st = btc_state.reindex(d.index).to_numpy()

    rows = []
    for kind, lvl_arr, sgn in (("сопротивление", hi, +1), ("поддержка", lo, -1)):
        last = -10 ** 9
        for i in range(WEEK + 24, n - HOR - 1):
            L, a = lvl_arr[i], atr[i]
            if not (np.isfinite(L) and np.isfinite(a) and a > 0):
                continue
            # подошла, но ещё не закрылась за уровнем
            near = (L - h[i]) <= NEAR * a if sgn > 0 else (l[i] - L) <= NEAR * a
            inside = c[i] < L if sgn > 0 else c[i] > L
            if not (near and inside):
                continue
            if i - last < MIN_GAP:
                continue
            last = i

            brk = L + sgn * BREAK_B * a
            bnc = L - sgn * BOUNCE_B * a
            lab = None
            for k in range(i + 1, i + HOR + 1):
                hit_b = h[k] >= brk if sgn > 0 else l[k] <= brk
                hit_r = l[k] <= bnc if sgn > 0 else h[k] >= bnc
                if hit_b and hit_r:
                    lab = None; break          # оба в одном баре — исход неясен
                if hit_b:
                    lab = 1; break
                if hit_r:
                    lab = 0; break
            if lab is None:
                continue

            touches = 0
            for k in range(max(0, i - WEEK), i):
                if np.isfinite(atr[k]) and atr[k] > 0:
                    near_k = (L - h[k]) <= NEAR * atr[k] if sgn > 0 else (l[k] - L) <= NEAR * atr[k]
                    if near_k:
                        touches += 1
            seg = lvl_arr[max(0, i - WEEK):i + 1]
            same = np.flatnonzero(np.isclose(seg, L, rtol=1e-9))
            age = (len(seg) - 1 - same[0]) if len(same) else np.nan

            rows.append(dict(
                symbol=sym, ts=d.index[i], kind=kind, label=lab,
                touches=touches, age=float(age) if np.isfinite(age) else np.nan,
                approach=float((c[i] - c[i - 12]) / a) * sgn,
                vol_rel=float(v6[i] / vmed[i]) if np.isfinite(vmed[i]) and vmed[i] > 0 else np.nan,
                atr_rel=float(a / amed[i]) if np.isfinite(amed[i]) and amed[i] > 0 else np.nan,
                dist_ma=float((c[i] - sma[i]) / a) * sgn if np.isfinite(sma[i]) else np.nan,
                btc=st[i] if isinstance(st[i], str) else None,
                conf_m=float(abs(L - (hi_m[i] if sgn > 0 else lo_m[i])) / atr[i])
                       if np.isfinite(hi_m[i] if sgn > 0 else lo_m[i]) else np.nan,
                conf_q=float(abs(L - (hi_q[i] if sgn > 0 else lo_q[i])) / atr[i])
                       if np.isfinite(hi_q[i] if sgn > 0 else lo_q[i]) else np.nan,
            ))
    return rows


def btc_states(btc):
    c = btc["c"]
    r30 = c / c.shift(720) - 1.0
    return pd.Series(np.where(r30 > 0.10, "рост", np.where(r30 < -0.10, "падение", "вбок")),
                     index=c.index)


def report(df, feats):
    """Базовые частоты и сдвиг вероятности пробоя по каждому признаку."""
    base = df.label.mean()
    print(f"\nБАЗОВАЯ ЧАСТОТА ПРОБОЯ: {base:.1%}   событий {len(df):,}")
    for k, sub in df.groupby("kind"):
        print(f"   {k:<14} пробой {sub.label.mean():.1%}   событий {len(sub):,}")

    print(f"\n{'признак':<10}{'низ':>10}{'сред':>10}{'верх':>10}{'разрыв':>9}"
          f"{'время OOS':>11}{'символы OOS':>13}")
    keep = []
    tmid = df.ts.quantile(0.5)
    syms = sorted(df.symbol.unique())
    half = set(syms[::2])
    for f in feats:
        d = df[np.isfinite(df[f])]
        if len(d) < 2000:
            continue
        q = d[f].quantile([1 / 3, 2 / 3]).values
        if q[0] == q[1]:
            continue
        b = np.where(d[f] <= q[0], 0, np.where(d[f] <= q[1], 1, 2))
        m = [d.label[b == i].mean() for i in range(3)]
        gap = max(m) - min(m)
        hi_bin = int(np.argmax(m)); lo_bin = int(np.argmin(m))

        def sub_gap(mask):
            dd, bb = d[mask], b[mask.to_numpy()]
            if (bb == hi_bin).sum() < 200 or (bb == lo_bin).sum() < 200:
                return np.nan
            return float(dd.label[bb == hi_bin].mean() - dd.label[bb == lo_bin].mean())

        g_time = sub_gap(d.ts > tmid)
        g_sym = sub_gap(~d.symbol.isin(half))
        ok = gap >= 0.05 and g_time > 0.02 and g_sym > 0.02
        print(f"{f:<10}{m[0]:>10.1%}{m[1]:>10.1%}{m[2]:>10.1%}{gap:>9.1%}"
              f"{g_time:>11.1%}{g_sym:>13.1%}{'   ПРИНЯТ' if ok else ''}")
        if ok:
            keep.append(dict(feature=f, gap=round(gap, 4), oos_time=round(float(g_time), 4),
                             oos_symbol=round(float(g_sym), 4)))
    for f, lab in (("conf_m", "месячный"), ("conf_q", "квартальный")):
        if f not in df:
            continue
        d = df[np.isfinite(df[f])]
        same = d[d[f] <= 0.5]; other = d[d[f] > 0.5]
        if len(same) > 500 and len(other) > 500:
            print(f"\nуровень совпадает с {lab}: пробой {same.label.mean():.1%} "
                  f"({len(same):,} соб.)   не совпадает {other.label.mean():.1%} ({len(other):,})"
                  f"   разница {(same.label.mean()-other.label.mean())*100:+.1f} п.п.")
    if "btc" in df:
        print("\nсостояние битка:")
        for k, sub in df.dropna(subset=["btc"]).groupby("btc"):
            print(f"   {k:<9} пробой {sub.label.mean():.1%}   событий {len(sub):,}")
    return keep


def main():
    os.makedirs(OUT, exist_ok=True)
    data = load(H1)
    if "BTCUSDT" not in data:
        raise SystemExit("нет BTCUSDT")
    st = btc_states(data["BTCUSDT"])
    print(f"[данные] символов {len(data)}", flush=True)

    rows = []
    for i, (sym, d) in enumerate(data.items(), 1):
        try:
            rows += events_for(sym, d, st)
        except Exception:
            continue
        if i % 25 == 0:
            print(f"  обработано {i}/{len(data)}, событий {len(rows):,}", flush=True)
    df = pd.DataFrame(rows)
    df = df[np.isfinite(df.label)]
    print(f"[события] {len(df):,}", flush=True)

    feats = ["touches", "age", "approach", "vol_rel", "atr_rel", "dist_ma", "conf_m", "conf_q"]
    keep = report(df, feats)
    print(f"\nПРИНЯТО ПРИЗНАКОВ: {len(keep)}"
          + (f" -> {[k['feature'] for k in keep]}" if keep else " — ни один не пережил обе проверки"))

    df.to_csv(os.path.join(OUT, "events.csv.gz"), index=False, compression="gzip")
    json.dump(dict(n_events=int(len(df)), base_rate=float(df.label.mean()), accepted=keep),
              open(os.path.join(OUT, "summary.json"), "w"), ensure_ascii=False, indent=2)
    print(f"[сохранено] {OUT}/summary.json")


if __name__ == "__main__":
    main()
