#!/usr/bin/env python3
"""
forward_horizon_study.py — что происходит с ценой через 6 / 24 / 72 часа
после события. Проверка премиссы, а не стратегия.

Предрегистрация: research_lab/prereg/PREREG_HORIZON_STUDY_2026_08_11.md
Читать её ДО результатов. Пороги и критерий смерти объявлены там.

Движок НЕ импортирует ничего из strategies/ и bot/ — намеренно, чтобы
результат не наследовал дефекты монолита.

Запуск:
    python3 forward_horizon_study.py --h1dir <dir> --out <dir>
    python3 forward_horizon_study.py --selftest        # синтетика, ответ обязан быть нулём
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HOUR_MS = 3_600_000
HORIZONS = (6, 24, 72)

# --- зафиксировано предрегистрацией, не подбирать ---
# ПОПРАВКА 2026-08-11 (внесена ДО просмотра любых форвардных ходов, см.
# PREREG ... "Поправка 1"): исходное «ход за 24ч >= 3*ATR24» неоднозначно
# по единице. ATR24 — ЧАСОВОЙ размах, и 3*ATR24 = 0.8 сигмы суточного хода
# (срабатывает на 40% баров), а 3*ATR24*sqrt(24) = 3.9 сигмы (1 событие
# за 2.7 года). Оба вырожденные. Импульс переопределён самокалибрующимся
# квантилем собственного распределения символа — единицы исчезают.
IMPULSE_Q = 0.95         # ход за 24ч в верхних/нижних 5% своего распределения за 90д
LEVEL_LOOKBACK = 168     # уровень = экстремум прошлой недели
SWEEP_LOOKBACK = 72      # снос стопов = экстремум прошлых 3 суток
TREND_MA = 168           # тренд = SMA недели
ATR_N = 24
ATR_SLOW = 336
SQUEEZE_WIN = 2160       # 90 суток
SQUEEZE_Q = 0.10
DECLUSTER_H = 24         # не более одного события семейства на символ за сутки
BURN_IN_H = 24 * 30      # 30 суток после первого бара выбрасываются
MIN_COVERAGE = 0.95
N_MAJORS = 15
MAJOR_VOL_WINDOW_H = 24 * 90
REGIME_LOOKBACK = 720    # 30 суток
REGIME_BAND = 0.10
N_BOOT = 2000
BOOT_SEED = 20260811

COST_BPS = {6: 17.0, 24: 19.0, 72: 25.0}   # круг + фандинг, см. предрегистрацию
EFFECT_BPS_MIN = 40.0
T_MIN = 3.4


# ----------------------------------------------------------------------------
# загрузка
# ----------------------------------------------------------------------------
def load_panel(h1dir, t_start_ms, t_end_ms):
    """Все символы на общую часовую сетку. Возвращает dict матриц (символы x время)."""
    files = sorted(glob.glob(os.path.join(h1dir, "*.npz")))
    if not files:
        raise SystemExit(f"нет данных в {h1dir}")

    grid = np.arange(t_start_ms, t_end_ms + HOUR_MS, HOUR_MS, dtype=np.int64)
    pos = {t: i for i, t in enumerate(grid)}
    T = len(grid)

    syms, rows_o, rows_h, rows_l, rows_c, rows_v, first_ts = [], [], [], [], [], [], []
    for fp in files:
        sym = os.path.basename(fp)[:-4]
        z = np.load(fp)
        ts, oh = z["ts"], z["ohlcv"]
        sel = (ts >= t_start_ms) & (ts <= t_end_ms)
        if sel.sum() < 24 * 60:
            continue
        idx = np.fromiter((pos[t] for t in ts[sel]), dtype=np.int64, count=int(sel.sum()))
        row = np.full((5, T), np.nan, dtype=np.float32)
        row[:, idx] = oh[sel].T
        syms.append(sym)
        rows_o.append(row[0]); rows_h.append(row[1]); rows_l.append(row[2])
        rows_c.append(row[3]); rows_v.append(row[4])
        first_ts.append(int(ts.min()))   # первый бар ВООБЩЕ, не в окне — прокси листинга

    P = {
        "syms": np.array(syms),
        "grid": grid,
        "open": np.vstack(rows_o), "high": np.vstack(rows_h),
        "low": np.vstack(rows_l), "close": np.vstack(rows_c),
        "vol": np.vstack(rows_v),
        "first_ts": np.array(first_ts, dtype=np.int64),
    }
    return P


def _df(mat, grid, syms):
    return pd.DataFrame(mat.T, index=grid, columns=syms, dtype="float32")


def _trailing_q(df, win_h, q, step=6):
    """Скользящий квантиль ТОЛЬКО по прошлому, посчитанный на разреженной сетке.

    shift(1) обязателен: текущий бар не должен участвовать в собственном пороге.
    """
    s = df.shift(1).iloc[::step]
    out = s.rolling(max(win_h // step, 2), min_periods=max(win_h // (2 * step), 2)).quantile(q)
    return out.reindex(df.index).ffill()


# ----------------------------------------------------------------------------
# признаки
# ----------------------------------------------------------------------------
def build_features(P):
    grid, syms = P["grid"], P["syms"]
    C = _df(P["close"], grid, syms)
    H = _df(P["high"], grid, syms)
    L = _df(P["low"], grid, syms)
    V = _df(P["vol"], grid, syms)

    prev_c = C.shift(1)
    tr = pd.concat([(H - L), (H - prev_c).abs(), (L - prev_c).abs()]).groupby(level=0).max()
    tr = tr.reindex(C.index)
    atr = tr.ewm(alpha=1.0 / ATR_N, adjust=False, min_periods=ATR_N).mean()
    atr_slow = tr.ewm(alpha=1.0 / ATR_SLOW, adjust=False, min_periods=ATR_SLOW).mean()

    ret24 = C / C.shift(24) - 1.0
    sma = C.rolling(TREND_MA, min_periods=TREND_MA).mean()

    # уровни ПРОШЛОГО окна: shift(1) обязателен, иначе заглядывание вперёд
    hi_lvl = H.shift(1).rolling(LEVEL_LOOKBACK, min_periods=LEVEL_LOOKBACK).max()
    lo_lvl = L.shift(1).rolling(LEVEL_LOOKBACK, min_periods=LEVEL_LOOKBACK).min()
    hi_sw = H.shift(1).rolling(SWEEP_LOOKBACK, min_periods=SWEEP_LOOKBACK).max()
    lo_sw = L.shift(1).rolling(SWEEP_LOOKBACK, min_periods=SWEEP_LOOKBACK).min()

    # скользящие квантили считаются на 6-часовой сетке и разворачиваются
    # обратно: rolling.quantile на 26k x 137 иначе не считается за разумное
    # время. Окно и уровень квантиля при этом ровно те, что объявлены.
    ratio = atr / atr_slow
    sq_thr = _trailing_q(ratio, SQUEEZE_WIN, SQUEEZE_Q)

    # пороги импульса: собственные квантили 24ч-хода за 90д, только прошлое
    imp_hi = _trailing_q(ret24, SQUEEZE_WIN, IMPULSE_Q)
    imp_lo = _trailing_q(ret24, SQUEEZE_WIN, 1.0 - IMPULSE_Q)

    dollar_vol = V * C
    return dict(C=C, H=H, L=L, atr=atr, atr_slow=atr_slow, ret24=ret24, sma=sma,
                hi_lvl=hi_lvl, lo_lvl=lo_lvl, hi_sw=hi_sw, lo_sw=lo_sw,
                ratio=ratio, sq_thr=sq_thr, imp_hi=imp_hi, imp_lo=imp_lo,
                dollar_vol=dollar_vol)


def rolling_fwd_extremes(F, h):
    """max(high) и min(low) по барам t+1..t+h, честно и без хвостовой утечки."""
    H, L, C = F["H"], F["L"], F["C"]
    fut_hi = H.shift(-h).rolling(h, min_periods=1).max()
    fut_lo = L.shift(-h).rolling(h, min_periods=1).min()
    return np.log(fut_hi / C), np.log(fut_lo / C)


# ----------------------------------------------------------------------------
# события
# ----------------------------------------------------------------------------
def build_events(F, eligible):
    C, H, L = F["C"], F["H"], F["L"]
    atr, ret24, sma = F["atr"], F["ret24"], F["sma"]

    ev = {}
    ev["IMPULSE_UP"] = ret24 >= F["imp_hi"]
    ev["IMPULSE_DN"] = ret24 <= F["imp_lo"]

    ev["BREAK_HI"] = C > F["hi_lvl"]
    ev["BREAK_LO"] = C < F["lo_lvl"]

    ev["TOUCH_HI"] = (H >= F["hi_lvl"]) & (C < F["hi_lvl"])
    ev["TOUCH_LO"] = (L <= F["lo_lvl"]) & (C > F["lo_lvl"])

    ev["SWEEP_LO"] = (L < F["lo_sw"]) & (C > F["lo_sw"])
    ev["SWEEP_HI"] = (H > F["hi_sw"]) & (C < F["hi_sw"])

    ev["PULLBACK_UP"] = (C > sma) & (ret24 < 0)
    ev["PULLBACK_DN"] = (C < sma) & (ret24 > 0)

    ev["SQUEEZE"] = F["ratio"] <= F["sq_thr"]

    base = pd.DataFrame(False, index=C.index, columns=C.columns)
    base.iloc[::24] = True
    ev["ALL"] = base

    for k in ev:
        ev[k] = (ev[k].fillna(False)) & eligible
    return ev


# знак, с которым читается форвардный ход: +1 «ждём вверх», -1 «ждём вниз», 0 ненаправленное
EVENT_SIGN = {
    "IMPULSE_UP": +1, "IMPULSE_DN": -1,
    "BREAK_HI": +1, "BREAK_LO": -1,
    "TOUCH_HI": -1, "TOUCH_LO": +1,
    "SWEEP_LO": +1, "SWEEP_HI": -1,
    "PULLBACK_UP": +1, "PULLBACK_DN": -1,
    "SQUEEZE": 0,
    "ALL": +1,
}


def decluster(mask_df, gap=DECLUSTER_H):
    """Не более одного события на символ за gap часов. Иначе одно событие = gap событий."""
    out = np.zeros(mask_df.shape, dtype=bool)
    arr = mask_df.to_numpy()
    for j in range(arr.shape[1]):
        idx = np.flatnonzero(arr[:, j])
        if idx.size == 0:
            continue
        keep, last = [], -10 ** 9
        for t in idx:
            if t - last >= gap:
                keep.append(t)
                last = t
        out[np.array(keep, dtype=np.int64), j] = True
    return pd.DataFrame(out, index=mask_df.index, columns=mask_df.columns)


# ----------------------------------------------------------------------------
# статистика
# ----------------------------------------------------------------------------
def week_block_stats(values, weeks, n_boot=N_BOOT, seed=BOOT_SEED):
    """Среднее и t по блочному бутстрапу календарных недель.

    Недели берутся целиком по всем символам сразу — это снимает и временную
    (окна пересекаются), и поперечную (символы ходят вместе) корреляцию.
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weeks)
    ok = np.isfinite(v)
    v, w = v[ok], w[ok]
    n = len(v)
    if n < 30:
        return dict(n=n, n_weeks=0, mean=np.nan, se=np.nan, t=np.nan, median=np.nan, hit=np.nan)

    uw, inv = np.unique(w, return_inverse=True)
    k = len(uw)
    sums = np.bincount(inv, weights=v, minlength=k)
    cnts = np.bincount(inv, minlength=k).astype(np.float64)

    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(n_boot, k))
    bs = sums[pick].sum(axis=1) / np.maximum(cnts[pick].sum(axis=1), 1.0)
    mean = float(v.mean())
    se = float(bs.std(ddof=1))
    return dict(n=int(n), n_weeks=int(k), mean=mean, se=se,
                t=(mean / se if se > 0 else np.nan),
                median=float(np.median(v)), hit=float((v > 0).mean()))


# ----------------------------------------------------------------------------
# основной прогон
# ----------------------------------------------------------------------------
def run(h1dir, outdir, sig_start, sig_end, tag):
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()

    warm_start = sig_start - pd.Timedelta(hours=SQUEEZE_WIN + ATR_SLOW + 48)
    load_end = sig_end + pd.Timedelta(hours=max(HORIZONS) + 2)
    P = load_panel(h1dir, int(warm_start.value // 10 ** 6), int(load_end.value // 10 ** 6))
    grid_ts = pd.to_datetime(P["grid"], unit="ms", utc=True)
    print(f"[load] символов {len(P['syms'])}, часов {len(P['grid'])} ({time.time()-t0:.0f}s)", flush=True)

    F = build_features(P)
    for k in F:
        F[k].index = grid_ts
    C = F["C"]
    print(f"[feat] готово ({time.time()-t0:.0f}s)", flush=True)

    # --- допустимость бара ---
    have = C.notna()
    burn = pd.DataFrame(
        (P["grid"][None, :] >= (P["first_ts"][:, None] + BURN_IN_H * HOUR_MS)).T,
        index=grid_ts, columns=C.columns)
    in_window = (C.index >= sig_start) & (C.index <= sig_end)
    eligible = have & burn & F["atr"].notna() & F["sma"].notna()
    eligible.loc[~in_window, :] = False

    # Покрытие считается от СОБСТВЕННОГО начала символа, а не от начала окна.
    # Иначе фильтр выбрасывает всё, что листнулось после 2023-01, и мы получаем
    # выборку только из старых выживших — то есть survivorship наоборот.
    win_idx = np.flatnonzero(in_window)
    grid_ms = P["grid"]
    sym_start = np.maximum(P["first_ts"] + BURN_IN_H * HOUR_MS, grid_ms[win_idx[0]])
    have_np = have.to_numpy()
    cov = {}
    for j, s in enumerate(C.columns):
        lo = np.searchsorted(grid_ms, sym_start[j])
        hi = win_idx[-1] + 1
        exp = hi - lo
        cov[s] = (have_np[lo:hi, j].sum() / exp) if exp >= 24 * 60 else 0.0
    cov = pd.Series(cov)
    keep_syms = cov[cov >= MIN_COVERAGE].index
    eligible.loc[:, ~C.columns.isin(keep_syms)] = False
    print(f"[filt] символов с покрытием >= {MIN_COVERAGE}: {len(keep_syms)}", flush=True)

    # --- группы: топ-15 по обороту за первые 90 дней окна (только прошлое) ---
    dv = F["dollar_vol"]
    first90 = (C.index >= sig_start) & (C.index < sig_start + pd.Timedelta(hours=MAJOR_VOL_WINDOW_H))
    med_dv = dv.loc[first90, keep_syms].median().sort_values(ascending=False)
    majors = set(med_dv.head(N_MAJORS).index)
    group = pd.Series(["major" if s in majors else "alt" for s in C.columns], index=C.columns)
    print(f"[grp] мажоры: {sorted(majors)}", flush=True)

    # --- режим по BTC ---
    btc = "BTCUSDT" if "BTCUSDT" in C.columns else med_dv.index[0]
    btc_ret = C[btc] / C[btc].shift(REGIME_LOOKBACK) - 1.0
    regime = pd.Series(np.where(btc_ret > REGIME_BAND, "bull",
                       np.where(btc_ret < -REGIME_BAND, "bear", "flat")), index=C.index)

    # --- форвардные ходы ---
    fwd, mfe, mae = {}, {}, {}
    for h in HORIZONS:
        fwd[h] = np.log(C.shift(-h) / C)
        fh, fl = rolling_fwd_extremes(F, h)
        mfe[h], mae[h] = fh, fl
    xs_mean = {h: fwd[h][keep_syms].mean(axis=1) for h in HORIZONS}
    btc_fwd = {h: fwd[h][btc] for h in HORIZONS}
    print(f"[fwd] готово ({time.time()-t0:.0f}s)", flush=True)

    # --- события ---
    events = build_events(F, eligible)
    weeks = pd.Series(C.index.isocalendar().year.astype(int) * 100 +
                      C.index.isocalendar().week.astype(int), index=C.index)

    rows = []
    for name, mask in events.items():
        m = decluster(mask)
        sign = EVENT_SIGN[name]
        ti, si = np.nonzero(m.to_numpy())
        if len(ti) == 0:
            continue
        cols = m.columns.to_numpy()[si]
        ev_group = group.reindex(cols).to_numpy()
        ev_week = weeks.to_numpy()[ti]
        ev_regime = regime.to_numpy()[ti]
        ev_atr = F["atr"].to_numpy()[ti, si]
        ev_px = C.to_numpy()[ti, si]

        for h in HORIZONS:
            f = fwd[h].to_numpy()[ti, si]
            up = mfe[h].to_numpy()[ti, si]
            dn = mae[h].to_numpy()[ti, si]
            xs = f - xs_mean[h].to_numpy()[ti]
            bt = f - btc_fwd[h].to_numpy()[ti]

            s = sign if sign != 0 else 1
            f_s, xs_s, bt_s = s * f, s * xs, s * bt
            fav = up if sign >= 0 else -dn
            adv = -dn if sign >= 0 else up
            atr_unit = (ev_atr / ev_px)
            with np.errstate(divide="ignore", invalid="ignore"):
                f_atr = f_s / atr_unit
                fav_atr = np.abs(fav) / atr_unit
                adv_atr = np.abs(adv) / atr_unit

            for grp in ("major", "alt", "both"):
                gsel = np.ones(len(f), bool) if grp == "both" else (ev_group == grp)
                for reg in ("all", "bull", "bear", "flat"):
                    rsel = gsel if reg == "all" else (gsel & (ev_regime == reg))
                    if rsel.sum() < 30:
                        continue
                    st = week_block_stats(f_s[rsel] * 1e4, ev_week[rsel])
                    stx = week_block_stats(xs_s[rsel] * 1e4, ev_week[rsel])
                    stb = week_block_stats(bt_s[rsel] * 1e4, ev_week[rsel])
                    rows.append(dict(
                        event=name, horizon_h=h, group=grp, regime=reg, sign=sign,
                        n=st["n"], n_weeks=st["n_weeks"],
                        raw_bps=st["mean"], raw_t=st["t"], raw_median=st["median"], hit=st["hit"],
                        xs_bps=stx["mean"], xs_t=stx["t"],
                        btc_bps=stb["mean"], btc_t=stb["t"],
                        mfe_atr=float(np.nanmean(fav_atr[rsel])),
                        mae_atr=float(np.nanmean(adv_atr[rsel])),
                        move_atr=float(np.nanmean(f_atr[rsel])),
                        cost_bps=COST_BPS[h],
                    ))
        print(f"[ev] {name:12s} событий={int(m.to_numpy().sum()):6d} ({time.time()-t0:.0f}s)", flush=True)

    res = pd.DataFrame(rows)
    res["mfe_mae"] = res["mfe_atr"] / res["mae_atr"].replace(0, np.nan)
    res["excess_over_ALL"] = np.nan
    for (h, grp, reg), sub in res.groupby(["horizon_h", "group", "regime"]):
        base = sub.loc[sub["event"] == "ALL", "raw_bps"]
        if len(base):
            res.loc[sub.index, "excess_over_ALL"] = sub["raw_bps"] - float(base.iloc[0])

    out_csv = os.path.join(outdir, f"horizon_study_{tag}.csv")
    res.to_csv(out_csv, index=False)

    meta = dict(tag=tag, generated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                sig_start=str(sig_start), sig_end=str(sig_end),
                n_symbols=int(len(keep_syms)), majors=sorted(majors),
                btc_proxy=btc, n_rows=int(len(res)),
                params=dict(IMPULSE_Q=IMPULSE_Q, LEVEL_LOOKBACK=LEVEL_LOOKBACK,
                            SWEEP_LOOKBACK=SWEEP_LOOKBACK, TREND_MA=TREND_MA,
                            DECLUSTER_H=DECLUSTER_H, BURN_IN_H=BURN_IN_H,
                            N_BOOT=N_BOOT, T_MIN=T_MIN, EFFECT_BPS_MIN=EFFECT_BPS_MIN))
    with open(os.path.join(outdir, f"horizon_study_{tag}_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    print(f"[done] {out_csv}  строк={len(res)}  ({time.time()-t0:.0f}s)", flush=True)
    return res


# ----------------------------------------------------------------------------
# самопроверка: на случайном блуждании ответ обязан быть нулём
# ----------------------------------------------------------------------------
def selftest(tmpdir):
    os.makedirs(tmpdir, exist_ok=True)
    rng = np.random.default_rng(7)
    t0 = int(pd.Timestamp("2022-10-01", tz="UTC").value // 10 ** 6)
    n = 24 * 900
    for i in range(40):
        ts = t0 + np.arange(n, dtype=np.int64) * HOUR_MS
        r = rng.normal(0, 0.004, n)
        c = 100 * np.exp(np.cumsum(r))
        o = np.r_[c[0], c[:-1]]
        wig = np.abs(rng.normal(0, 0.002, n)) * c
        h = np.maximum(o, c) + wig
        l = np.minimum(o, c) - wig
        v = rng.lognormal(10, 1, n)
        np.savez_compressed(os.path.join(tmpdir, f"SYN{i:03d}USDT.npz"),
                            ts=ts, ohlcv=np.column_stack([o, h, l, c, v]).astype(np.float32),
                            nsub=np.full(n, 12, dtype=np.int16))
    res = run(tmpdir, os.path.join(tmpdir, "out"),
              pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2024-12-31", tz="UTC"), "selftest")
    m = res[(res.group == "both") & (res.regime == "all")]
    worst = m.reindex(m["raw_t"].abs().sort_values(ascending=False).index).head(8)
    print("\n=== САМОПРОВЕРКА: случайное блуждание, ожидание — ноль ===")
    print(worst[["event", "horizon_h", "n", "n_weeks", "raw_bps", "raw_t", "xs_bps", "xs_t"]]
          .to_string(index=False, float_format=lambda x: f"{x:8.2f}"))
    bad = worst[worst["raw_t"].abs() > T_MIN]
    print("\nВЕРДИКТ:", "ПРОВАЛ — движок находит эдж там, где его нет"
          if len(bad) else "ОК — на синтетике ноль, движок не выдумывает")
    return len(bad) == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1dir", default="research_lab/data/h1")
    ap.add_argument("--out", default="research_lab/results/horizon_study")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-09-27")
    ap.add_argument("--tag", default="main")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        ok = selftest("/tmp/hz_selftest")
        sys.exit(0 if ok else 1)

    run(a.h1dir, a.out,
        pd.Timestamp(a.start, tz="UTC"), pd.Timestamp(a.end, tz="UTC"), a.tag)
