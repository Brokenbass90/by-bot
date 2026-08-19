#!/usr/bin/env python3
"""antileg.py — есть ли что торговать в тот момент, когда нас выбивает.

ИДЕЯ ВЛАДЕЛЬЦА: красные месяцы делает частота стопов (17.5% против 10%).
Стоп у шорта во флете вниз — это импульс ВВЕРХ. Если такой импульс
имеет продолжение, то на том же самом событии можно зарабатывать
противоположной ногой. Тогда плохие для основной ноги периоды
становятся хорошими для встречной, и просадка сглаживается.

ЧТО ПРОВЕРЯЕМ. Берём момент, когда сделка основной ноги закрылась
стопом, и входим в ПРОТИВОПОЛОЖНУЮ сторону по открытию следующего
часа с той же геометрией (тот же стоп в процентах цены, те же цели
в единицах риска, то же удержание).

Контроль обязателен: сравниваем со случайным входом в тот же месяц
по той же монете с той же геометрией. Иначе измерим не эдж,
а движение рынка.

КРИТЕРИЙ, ОБЪЯВЛЕННЫЙ ДО ПРОГОНА: встречная нога принимается,
только если эдж над случайным входом положителен НА ОБОИХ окнах.
Дополнительно смотрим корреляцию помесячных итогов с основной ногой:
чем она отрицательнее, тем ценнее нога как диверсификатор.
"""
from __future__ import annotations
import glob, importlib, json, math, os, sys, datetime as dt
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
sys.path.insert(0, ROOT); sys.path.insert(0, f"{ROOT}/research_lab")
from research_machine import Store, ema, simulate
from random_control import sim_geo

WINDOWS = {"2024-03..2025-09": (1709251200000, 1759276800000),
           "2023-01..2024-02": (1672531200000, 1709251200000)}
SEAL = 1759276800000
FLAT, DRAWS = 0.02, 10
LEGS = [("alt_trendline_touch_v1", "AltTrendlineTouchV1Strategy", "ATT1",
         "short", 6.0, 336, "флет-", "8"),
        ("sloped_break_retest_v1", "SlopedBreakRetestV1Strategy", "SBR1",
         "long", 4.0, 168, "флет+", "0")]


def main():
    files = sorted(glob.glob(f"{DATA}/*.npz"))
    d = np.load(f"{DATA}/BTCUSDT.npz")
    c = d["ohlcv"][:, 3].astype(float); em = ema(c, 200)
    bts, bdist = d["ts"], (c - em) / em

    def reg(t, want):
        j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
        v = float(bdist[j]) if j < len(bdist) else 0.0
        return (-FLAT <= v < 0) if want == "флет-" else (0 <= v < FLAT)

    for mod, cls, pfx, side, mult, hold, rg, cd in LEGS:
        for k in list(os.environ):
            if k.startswith(pfx + "_"):
                del os.environ[k]
        os.environ.update({f"{pfx}_SYMBOL_ALLOWLIST": ",".join(Path(f).stem for f in files),
                           f"{pfx}_ALLOW_LONGS": "1", f"{pfx}_ALLOW_SHORTS": "1"})
        if cd != "0":
            os.environ[f"{pfx}_COOLDOWN_BARS_5M"] = cd
        for m in list(sys.modules):
            if m.startswith("strategies."):
                del sys.modules[m]
        S = getattr(importlib.import_module(f"strategies.{mod}"), cls)
        anti_side = "long" if side == "short" else "short"
        real = {w: [] for w in WINDOWS}
        ctrl = {w: [[] for _ in range(DRAWS)] for w in WINDOWS}
        main_m, anti_m = {}, {}
        rng = np.random.default_rng(3)
        for fp in files:
            dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
            msk = ts < SEAL
            ts, o = ts[msk], o[msk]
            if len(ts) < 500:
                continue
            bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                    for x in range(len(ts))]
            month = (ts // (30 * 86400000)).astype(np.int64)
            st = Store(Path(fp).stem); strat = S(); block = -1
            for i in range(120, len(bars) - 2):
                st.rows = bars[: i + 1]; b = bars[i]
                try:
                    s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
                except Exception:
                    continue
                if s is None or s.side != side or i <= block or not reg(b[0], rg):
                    continue
                r = simulate(bars, i, side, s.sl, list(s.tps or []),
                             (s.tp_fracs or [0.55])[0], mult, hold)
                if r is None:
                    continue
                block = i + r["bars"] + 1
                mk = dt.datetime.utcfromtimestamp(b[0] / 1000).strftime("%Y-%m")
                main_m.setdefault(mk, []).append(r["R"])
                # интересует только выбитая стопом сделка
                if r["R"] > -0.85:
                    continue
                j = i + r["bars"]           # бар, на котором выбило
                if j + 2 >= len(bars):
                    continue
                e0 = float(bars[j + 1][1])
                sp = 1.0 / r["lev"]         # то же расстояние до стопа в долях цены
                rc = sim_geo(bars, j, anti_side == "short", sp, 1.2, 2.5, 0.55, hold)
                if rc is None:
                    continue
                anti_m.setdefault(mk, []).append(rc)
                for w, (a, b2) in WINDOWS.items():
                    if a <= bars[j][0] < b2:
                        real[w].append(rc)
                        pool = np.flatnonzero((month == month[j]) &
                                              (np.arange(len(ts)) >= 120) &
                                              (np.arange(len(ts)) < len(ts) - 2))
                        if len(pool) < 5:
                            continue
                        for dr in range(DRAWS):
                            x = sim_geo(bars, int(rng.choice(pool)), anti_side == "short",
                                        sp, 1.2, 2.5, 0.55, hold)
                            if x is not None:
                                ctrl[w][dr].append(x)

        print(f"\n╔══ встречная нога к {pfx}: вход в {anti_side} сразу после выбитого стопа")
        print(f"{'окно':<20}{'n':>6}{'встречная':>12}{'случайно':>12}{'ЭДЖ':>12}{'σ':>8}")
        for w in WINDOWS:
            R = np.array(real[w])
            cm = np.array([np.mean(x) for x in ctrl[w] if len(x) > 20])
            if len(R) < 50 or len(cm) < 3:
                print(f"{w:<20} сделок мало"); continue
            edge = R.mean() - cm.mean()
            se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
            print(f"{w:<20}{len(R):>6}{R.mean():>+11.4f}R{cm.mean():>+11.4f}R"
                  f"{edge:>+11.4f}R{edge/se:>+8.2f}")
        common = sorted(set(main_m) & set(anti_m))
        if len(common) >= 8:
            a = np.array([np.sum(main_m[m]) for m in common])
            bq = np.array([np.sum(anti_m[m]) for m in common])
            print(f"  корреляция помесячных итогов основной и встречной ноги: "
                  f"{np.corrcoef(a, bq)[0,1]:+.2f}  (месяцев {len(common)})")
            print(f"  месяцев, где основная в минусе, а встречная в плюсе: "
                  f"{int(((a<0)&(bq>0)).sum())} из {int((a<0).sum())}")


if __name__ == "__main__":
    main()
