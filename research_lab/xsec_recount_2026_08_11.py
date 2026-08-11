#!/usr/bin/env python3
"""
xsec_recount_2026_08_11.py — честный пересчёт XSEC на 3.5 годах.

Что чинит по сравнению с опубликованным V4:
  * ЗРЕЛОСТЬ по фактическому первому бару символа, а не по длине локального
    файла. Порог считается КРИВОЙ (180/270/390/540), а не точкой: в V4 порог
    390 был подобран на исходе (180 -> 1.75, 270 -> 1.32, 390 -> 2.73).
  * ГОДОВОЙ SHARPE считается как mu/sd*sqrt(365/R). В исходном коде метрика
    `sh` = mu/sd*sqrt(n) — это t-статистика. На выборке ровно в 1 год они
    численно совпадают (sqrt(117) ~ sqrt(365/3)), на 3.5 годах — нет,
    и та же формула выдала бы ~5.1 из ниоткуда. Печатаются обе, раздельно.
  * УСТОЙЧИВОСТЬ ВО ВРЕМЕНИ: скользящий Sharpe за 6 месяцев по всему периоду,
    чтобы видеть затухание, а не одно число за всё время.
  * КАПИТАЛ: сколько денег нужно рукаву. Позиции ниже минимального номинала
    отбрасываются, и меряется, что это делает с результатом.

Логика решения НЕ ТРОГАЕТСЯ: используется research_lab/xsec_v3_reference.py
как есть (это и есть эталон, который автор просил портировать), плюс оба
фильтра V4 оттуда же. Совпадение конвенции издержек с xsec_eventfilter.py:
15 bps на ребаланс (2*MAKER + 2*TAKER, MAKER=2bps, TAKER=5.5bps).

Предрегистрация: research_lab/prereg/PREREG_XSEC_RECOUNT_2026_08_11.md
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    import xsec_v3_reference as X
except ImportError:
    from research_lab import xsec_v3_reference as X

R = X.REBALANCE_DAYS
K = X.K
LOOK = X.LOOKBACKS
COST_PER_REBAL = 2 * 0.0002 + 2 * 0.00055      # 15 bps, как в xsec_eventfilter
TV = X.TARGET_ANNUAL_VOL
MIN_UNIV = X.MIN_UNIVERSE


# ---------------------------------------------------------------- данные
def load_daily(h1dir, search_end):
    """Дневные закрытия UTC из часового бандла + фактический первый бар."""
    ser, first = {}, {}
    cutoff = pd.Timestamp(search_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    for fp in sorted(glob.glob(os.path.join(h1dir, "*.npz"))):
        sym = os.path.basename(fp)[:-4]
        z = np.load(fp)
        s = pd.Series(z["ohlcv"][:, 3].astype("float64"),
                      index=pd.to_datetime(z["ts"], unit="ms", utc=True))
        d = s.loc[:cutoff].resample("1D").last().dropna()
        if len(d) < 120:
            continue
        ser[sym] = d
        first[sym] = d.index[0]
    px = pd.DataFrame(ser).sort_index()
    return px, pd.Series(first)


# ---------------------------------------------------------------- ядро
def run_phase(px, first_day, mat_days, start_offset, f1=True, f2=True,
              cost=COST_PER_REBAL, min_notional=0.0, gross_usd=0.0):
    """Одна фаза (подпортфель). Возвращает список доходностей за ребаланс."""
    cols = px.columns.to_numpy()
    P = px.to_numpy()
    idx = px.index
    N = len(idx)
    need = max(LOOK) + 1
    age_ok = np.zeros((N, len(cols)), dtype=bool)
    fd = first_day.reindex(cols).to_numpy()
    for j in range(len(cols)):
        age_ok[:, j] = (idx - fd[j]).days >= mat_days

    # медиана |дневной доходности| по универсуму — для фильтра F2
    dr = np.abs(P[1:] / P[:-1] - 1.0)
    med_abs = np.full(N, np.nan)
    med_abs[1:] = np.nanmedian(np.where(np.isfinite(dr), dr, np.nan), axis=1)

    # ВАЖНО: сетка ребалансов обязана оставаться регулярной. Любой пропуск
    # записывается как 0.0 (сидим в кэше), а не выбрасывается из ряда —
    # иначе календарь сдвигается и погодовая разбивка врёт. На этом я уже
    # один раз попался в этом же прогоне.
    out, ncounts, drops, dates, skips = [], [], [], [], []
    for i in range(max(start_offset, need + 2), N - R - 1, R):
        dates.append(idx[i])
        if f2:
            hist = med_abs[max(1, i - 60):i]
            hist = hist[np.isfinite(hist)]
            if len(hist) >= 30 and np.isfinite(med_abs[i]):
                if X.is_market_stress(list(hist), float(med_abs[i])):
                    out.append(0.0)          # ребаланс пропущен целиком
                    ncounts.append(0)
                    drops.append(0)
                    skips.append("stress")
                    continue

        hist_map = {}
        for j, s in enumerate(cols):
            if not age_ok[i, j]:
                continue
            c = P[max(0, i - need + 1):i + 1, j]
            if len(c) < need or not np.all(np.isfinite(c)) or c[-1] <= 0:
                continue
            cl = list(c)
            if f1 and X.is_post_event_noise(cl, max(LOOK)):
                continue
            hist_map[s] = cl

        if len(hist_map) < MIN_UNIV:
            out.append(0.0); ncounts.append(0); drops.append(0); skips.append("universe")
            continue
        w = X.target_weights(hist_map)
        if not w:
            out.append(0.0); ncounts.append(0); drops.append(0); skips.append("noweights")
            continue

        dropped = 0
        if min_notional > 0 and gross_usd > 0:
            g = sum(abs(v) for v in w.values())
            keep = {}
            for s, v in w.items():
                if abs(v) / g * gross_usd >= min_notional:
                    keep[s] = v
                else:
                    dropped += 1
            w = keep
            if not w:
                out.append(0.0); ncounts.append(0); drops.append(dropped); skips.append("minnotional")
                continue

        ret = 0.0
        for s, v in w.items():
            j = int(np.flatnonzero(cols == s)[0])
            p1, p2 = P[i, j], P[i + R, j]
            if not (np.isfinite(p1) and np.isfinite(p2) and p1 > 0):
                continue
            ret += v * (p2 / p1 - 1.0)
        out.append(ret - cost)
        ncounts.append(len(w))
        drops.append(dropped)
        skips.append("")
    return out, ncounts, drops, dates, skips


def vol_target(r, win=X.VOL_WINDOW_REBALANCES):
    o = []
    for i, x in enumerate(r):
        h = r[max(0, i - win):i]
        if len(h) < 8:
            o.append(x * 0.5)
            continue
        sd = float(np.std(h, ddof=1))
        ann = sd * np.sqrt(365.0 / R)
        o.append(x * (min(1.0, TV / ann) if ann > 0 else 1.0))
    return o


def metrics(r):
    r = np.asarray(r, dtype=float)
    if len(r) < 8:
        return dict(n=len(r), tot=np.nan, dd=np.nan, sharpe_ann=np.nan, tstat=np.nan)
    eq = np.cumprod(1 + r)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    years = len(r) * R / 365.0
    return dict(
        n=len(r),
        tot=round(float(eq[-1] - 1) * 100, 1),
        cagr=round((float(eq[-1]) ** (1 / years) - 1) * 100, 1) if years > 0 else np.nan,
        dd=round(dd * 100, 1),
        sharpe_ann=round(mu / sd * np.sqrt(365.0 / R), 2) if sd > 0 else 0.0,
        tstat=round(mu / sd * np.sqrt(len(r)), 2) if sd > 0 else 0.0,
        years=round(years, 2),
    )


def combined(px, first_day, mat_days, **kw):
    """Три сдвинутые фазы -> один ряд, ВЫРОВНЕННЫЙ ПО ДАТАМ, а не по индексу."""
    phases, counts, drops, allskips = [], [], [], []
    for off in (0, 1, 2):
        r, nc, dr, dt, sk = run_phase(px, first_day, mat_days, max(LOOK) + 2 + off, **kw)
        phases.append(pd.Series(vol_target(r), index=pd.DatetimeIndex(dt)))
        counts += nc
        drops += dr
        allskips += sk
    if not phases or all(len(p) == 0 for p in phases):
        return pd.Series(dtype=float), [], counts, drops, allskips
    # Конструкция та же, что в xsec_eventfilter (капитал делится на 3 фазы,
    # i-е элементы усредняются) — иначе результат несравним с опубликованным.
    # Единственное отличие: ряду присваиваются РЕАЛЬНЫЕ даты фазы 0, поэтому
    # погодовая разбивка честная. Фазы сдвинуты на 1-2 дня, для годовых
    # и полугодовых срезов этой точности с запасом.
    m = min(len(p) for p in phases)
    vals = [float(sum(p.iloc[i] for p in phases) / len(phases)) for i in range(m)]
    comb = pd.Series(vals, index=phases[0].index[:m])
    return comb, phases, counts, drops, allskips


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1dir", default="research_lab/data/h1")
    ap.add_argument("--out", default="research_lab/results/xsec_recount")
    ap.add_argument("--search-end", default="2025-09-30")
    ap.add_argument("--reveal-modern", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.reveal_modern:
        raise SystemExit(
            "ОТКАЗ: reserved 2025-10..2026-06 holdout закрыт; "
            "этот скрипт больше не имеет права его вскрывать"
        )
    os.makedirs(a.out, exist_ok=True)

    px_all, first_day = load_daily(a.h1dir, a.search_end)
    print(f"[load] символов {px_all.shape[1]}, дней {px_all.shape[0]} "
          f"({px_all.index[0].date()} .. {px_all.index[-1].date()})", flush=True)

    px_search = px_all.loc[:a.search_end]
    results = {
        "_meta": {
            "schema_id": "xsec_recount_search_only_v2",
            "search_end_utc": a.search_end,
            "reserved_holdout_used": False,
            "prior_modern_result_status": "QUARANTINED_HOLDOUT_CONTAMINATION",
        }
    }

    # ---- 1. кривая порога зрелости на окне поиска ----
    print(f"\n=== ОКНО ПОИСКА {px_search.index[0].date()} .. {px_search.index[-1].date()} ===")
    print(f"{'зрелость':>9} {'символов':>9} {'ребал':>6} {'итог%':>8} {'CAGR%':>7} "
          f"{'DD%':>6} {'Sharpe':>7} {'t':>6}")
    curve = {}
    for mat in (180, 270, 390, 540):
        n_sym = int(((px_search.index[-1] - first_day).dt.days >= mat).sum())
        comb, _, counts, _, sk = combined(px_search, first_day, mat)
        if len(comb) < 8:
            print(f"{mat:>9} {n_sym:>9} {'--':>6}  универсума не хватает")
            curve[mat] = None
            continue
        m = metrics(comb.values)
        m["skipped_stress"] = sum(1 for x in sk if x == "stress")
        m["skipped_universe"] = sum(1 for x in sk if x == "universe")
        curve[mat] = m
        print(f"{mat:>9} {n_sym:>9} {m['n']:>6} {m['tot']:>8} {m['cagr']:>7} "
              f"{m['dd']:>6} {m['sharpe_ann']:>7} {m['tstat']:>6}   "
              f"пропущено: стресс {m['skipped_stress']}, универсум {m['skipped_universe']}")
    results["maturity_curve_search"] = curve

    # ---- 2. устойчивость во времени на выбранной зрелости ----
    ref_mat = 390
    comb, phases, counts, _, sk = combined(px_search, first_day, ref_mat)
    s = comb
    print(f"\n=== ПОГОДОВАЯ УСТОЙЧИВОСТЬ (зрелость {ref_mat}д, окно поиска) ===")
    print(f"{'период':>10} {'ребал':>6} {'итог%':>8} {'Sharpe':>7} {'t':>6}")
    yearly = {}
    for y, sub in s.groupby(s.index.year):
        if len(sub) >= 8:
            mm = metrics(sub.values)
            yearly[int(y)] = mm
            print(f"{y:>10} {mm['n']:>6} {mm['tot']:>8} {mm['sharpe_ann']:>7} {mm['tstat']:>6}")
    results["yearly_search"] = yearly

    # скользящий Sharpe за 6 месяцев (60 ребалансов)
    win = 60
    roll = []
    for i in range(win, len(s) + 1):
        sub = s.values[i - win:i]
        sd = sub.std(ddof=1)
        roll.append((s.index[i - 1], (sub.mean() / sd * np.sqrt(365.0 / R)) if sd > 0 else 0.0))
    rs = pd.Series(dict(roll))
    if len(rs):
        print(f"\nскользящий Sharpe за 6 мес: медиана {rs.median():.2f}, "
              f"мин {rs.min():.2f}, макс {rs.max():.2f}, доля окон >0: {(rs>0).mean():.0%}")
        print("последние 5 окон:", ", ".join(f"{v:.2f}" for v in rs.values[-5:]))
        results["rolling6m"] = {str(k.date()): round(float(v), 3) for k, v in rs.items()}

    # ---- 3. капитал: минимальный номинал позиции ----
    print(f"\n=== КАПИТАЛ РУКАВА (зрелость {ref_mat}д, окно поиска) ===")
    _live = [x for x in counts if x > 0]
    print(f"позиций за ребаланс (без пропущенных): медиана {int(np.median(_live))}, "
          f"диапазон {min(_live)}-{max(_live)}; пропущено ребалансов {len(counts)-len(_live)} из {len(counts)}")
    print(f"{'эквити$':>9} {'валовая$':>9} {'$/поз':>7}   " + "   ".join(f"мин${m}" for m in (5,10,25,50)))
    print("  (в клетке: итоговая доходность / доля отброшенных позиций)")
    cap_rows = []
    base = metrics(comb.values)
    print("минимальный номинал заявки, $:  5 / 10 / 25 / 50")
    for eq in (250, 500, 1000, 2000, 5000):
        gross = eq * 2.0                      # 1.0 лонг + 1.0 шорт при плече 1.0
        row = {"equity": eq, "gross": gross}
        cells = []
        for mn in (5.0, 10.0, 25.0, 50.0):
            c2, _, cnt2, dr2, _ = combined(px_search, first_day, ref_mat,
                                           min_notional=mn, gross_usd=gross)
            if len(c2) < 8:
                cells.append("--"); continue
            m2 = metrics(c2.values)
            live = [x for x in cnt2 if x > 0]
            med_n = int(np.median(live)) if live else 0
            med_drop = float(np.mean(dr2)) if dr2 else 0.0
            frac = med_drop / max(med_n + med_drop, 1)
            row[f"mn{int(mn)}"] = dict(tot=m2["tot"], sharpe=m2["sharpe_ann"],
                                       dropped_frac=round(frac, 3), positions=med_n)
            cells.append(f"{m2['tot']:>6.1f}%/{frac:>4.0%}")
        live0 = [x for x in counts if x > 0]
        pp = gross / max(int(np.median(live0)) if live0 else 1, 1)
        print(f"{eq:>9} {gross:>9.0f} {pp:>7.0f}   " + "  ".join(cells))
        cap_rows.append(row)
    print(f"{'без пола':>9} {'':>9} {'':>7}   {base['tot']:>6.1f}%/  0%")
    results["capital"] = cap_rows
    results["baseline_search"] = base

    with open(os.path.join(a.out, "xsec_recount.json"), "w") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False, default=str)
    print(f"\n[done] -> {a.out}/xsec_recount.json")


if __name__ == "__main__":
    main()
