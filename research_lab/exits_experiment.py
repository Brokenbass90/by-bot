#!/usr/bin/env python3
"""exits_experiment.py — безубыток и трейлинг, объявленный эксперимент.

ПРАВИЛА ОБЪЯВЛЕНЫ ДО ПРОГОНА И НЕ ПОДБИРАЮТСЯ.

Машина до сих пор моделировала выход только тремя способами: стоп,
цели, время. В живом боте есть ещё два, и они меняют результат:

    безубыток   при +be_trigger_rr стоп переносится в вход + be_lock_rr
    трейлинг    при +trail_activate_rr включается стоп на ATR × trail_mult

Числа берутся ИЗ ЖИВОГО КОДА ATT1, а не подбираются:
    be_trigger_rr = 1.00   be_lock_rr = 0.02
    trail_activate_rr = 1.00   trail_atr_mult = 1.50   ATR период 14

Порог R считается от ФАКТИЧЕСКОГО риска сделки (стоп ×6), а не от
штатного. Это объявлено заранее: иначе при широком стопе безубыток
срабатывал бы почти сразу и правило перестало бы быть тем же самым.

Сравниваются четыре варианта на одной конфигурации:
    ATT1, шорт, стоп ×6, удержание 336 ч, BTC во флете вниз.

КРИТЕРИЙ, ОБЪЯВЛЕННЫЙ ЗАРАНЕЕ: вариант принимается, только если он
лучше базового НА ОБОИХ окнах. Лучше на одном — отклоняется.
"""
from __future__ import annotations
import glob, importlib, math, os, sys
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
WINDOWS = {"2024-03..2025-09": (1709251200000, 1759276800000),
           "2023-01..2024-02": (1672531200000, 1709251200000)}
MULT, HOLD, FEE_BPS_SIDE, LOOKBACK = 6.0, 336, 6.0, 120
BE_TRIGGER, BE_LOCK = 1.00, 0.02
TRAIL_ACTIVATE, TRAIL_ATR = 1.00, 1.50
ATR_N, FLAT = 14, 0.02
COOLDOWN = 8


class Store:
    def __init__(self, s):
        self.symbol = s
        self.rows = []

    def fetch_klines(self, sym, tf, n):
        return self.rows[-n:]


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; out = np.empty(len(x))
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def atr_series(o, n=ATR_N):
    h, l, c = o[:, 1], o[:, 2], o[:, 3]
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.empty(len(tr)); s = tr[:n].mean() if len(tr) >= n else tr.mean()
    for i, v in enumerate(tr):
        s = (s * (n - 1) + v) / n; out[i] = s
    return out


def simulate(bars, atr, i, side, sl0, tps, f1, use_be, use_trail):
    e = i + 1
    if e >= len(bars):
        return None
    entry = float(bars[e][1])
    short = side == "short"
    sl = entry + (sl0 - entry) * MULT
    risk = (sl - entry) if short else (entry - sl)
    if risk <= 0:
        return None
    lev = entry / risk
    cost = lev * 2 * FEE_BPS_SIDE / 1e4
    tp1, tp2 = (list(tps) + [None, None])[:2]
    stop, rem, gross, tp1_done = sl, 1.0, 0.0, False
    be_on = trail_on = False
    for j in range(e, min(e + HOLD, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        # 1) стоп проверяется первым — консервативно
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev)
        # 2) цели
        if tp1 and not tp1_done and ((l <= tp1) if short else (h >= tp1)):
            gross += f1 * ((entry - tp1) if short else (tp1 - entry)) / risk
            rem -= f1; tp1_done = True
        if tp2 and rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * ((entry - tp2) if short else (tp2 - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev)
        # 3) сколько прошли в свою сторону на этом баре
        best = l if short else h
        run = ((entry - best) if short else (best - entry)) / risk
        if use_be and not be_on and run >= BE_TRIGGER:
            be = entry - BE_LOCK * risk if short else entry + BE_LOCK * risk
            stop = min(stop, be) if short else max(stop, be)
            be_on = True
        if use_trail and run >= TRAIL_ACTIVATE:
            trail_on = True
        if trail_on:
            a = float(atr[j])
            t = best + TRAIL_ATR * a if short else best - TRAIL_ATR * a
            stop = min(stop, t) if short else max(stop, t)
    j = min(e + HOLD, len(bars)) - 1
    px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return dict(R=gross - cost, bars=j - e, lev=lev)


def main():
    sys.path.insert(0, ROOT)
    files = sorted(glob.glob(f"{DATA}/*.npz"))
    syms = ",".join(Path(f).stem for f in files)
    os.environ.update({"ATT1_SYMBOL_ALLOWLIST": syms, "ATT1_ALLOW_LONGS": "1",
                       "ATT1_ALLOW_SHORTS": "1",
                       "ATT1_COOLDOWN_BARS_5M": str(COOLDOWN)})
    S = getattr(importlib.import_module("strategies.alt_trendline_touch_v1"),
                "AltTrendlineTouchV1Strategy")
    d = np.load(f"{DATA}/BTCUSDT.npz")
    c = d["ohlcv"][:, 3].astype(float); em = ema(c, 200)
    bts, bdist = d["ts"], (c - em) / em

    def flat_down(t):
        j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
        v = float(bdist[j]) if j < len(bdist) else 0.0
        return -FLAT <= v < 0

    VAR = [("как сейчас", False, False), ("+ безубыток", True, False),
           ("+ трейлинг", False, True), ("+ оба", True, True)]
    res = {v[0]: {w: [] for w in WINDOWS} for v in VAR}
    for k, fp in enumerate(files):
        dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
        m = ts < 1759276800000
        ts, o = ts[m], o[m]
        if len(ts) < LOOKBACK + 300:
            continue
        atr = atr_series(o)
        bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                for x in range(len(ts))]
        st = Store(Path(fp).stem); strat = S()
        sigs = []
        for i in range(LOOKBACK, len(bars)):
            st.rows = bars[: i + 1]; b = bars[i]
            try:
                s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
            except Exception:
                continue
            if s is None or s.side != "short" or not flat_down(b[0]):
                continue
            sigs.append((i, s.sl, list(s.tps or []), (s.tp_fracs or [0.55])[0]))
        for name, ube, utr in VAR:
            block = -1
            for i, sl0, tps, f1 in sigs:
                if i <= block:
                    continue
                r = simulate(bars, atr, i, "short", sl0, tps, f1, ube, utr)
                if r is None:
                    continue
                block = i + r["bars"] + 1
                t = bars[i][0]
                for w, (a, b2) in WINDOWS.items():
                    if a <= t < b2:
                        res[name][w].append(r["R"])
        if (k + 1) % 40 == 0:
            print(f"... {k+1}/{len(files)}", flush=True)

    print("\nATT1, шорт, стоп ×6, удержание 336 ч, BTC во флете вниз")
    print(f"{'вариант':<14}{'окно':<20}{'n':>6}{'итог':>11}{'σ':>7}{'порог':>10}{'винрейт':>9}")
    base = {}
    for name, _, _ in VAR:
        for w in WINDOWS:
            R = np.array(res[name][w])
            if len(R) < 50:
                continue
            se = R.std(ddof=1) / math.sqrt(len(R))
            mde = 1.96 * R.std(ddof=1) / math.sqrt(len(R))
            if name == "как сейчас":
                base[w] = R.mean()
            print(f"{name:<14}{w:<20}{len(R):>6}{R.mean():>+10.4f}R"
                  f"{R.mean()/se:>+7.2f}{mde:>9.4f}R{(R>0).mean():>9.0%}")
        print()
    print("Изменение против базового варианта:")
    for name, _, _ in VAR[1:]:
        deltas = []
        for w in WINDOWS:
            R = np.array(res[name][w])
            if len(R) < 50 or w not in base:
                continue
            deltas.append((w, R.mean() - base[w]))
        ok = all(d > 0 for _, d in deltas) and len(deltas) == 2
        s = "  ".join(f"{w}: {d:+.4f}R" for w, d in deltas)
        print(f"  {name:<14}{s}   {'ПРИНЯТ' if ok else 'отклонён'}")


if __name__ == "__main__":
    main()
