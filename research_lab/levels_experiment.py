#!/usr/bin/env python3
"""levels_experiment.py — а не вяло ли система рисует горизонтальные уровни.

ПОДОЗРЕНИЕ ВЛАДЕЛЬЦА, СФОРМУЛИРОВАННОЕ ДО ПРОГОНА.

Что стоит в HZBO1 сейчас:
    signal_lookback = 150   уровни ищутся всего по 150 часам = 6 суток
    min_touches     = 2     зоной считаются ДВА пивота рядом
    max_zone_age    = 25    зона живёт 25 часов после последнего касания

Горизонтальный уровень в крипте — это недели и месяцы, а не шесть
суток. И два касания — это не уровень, это совпадение. Уровень
начинается с трёх.

ЧТО ПРОВЕРЯЕМ. Девять сочетаний, объявленных заранее:
    глубина истории  150 (как сейчас) / 400 / 800 часов
    касаний          2 (как сейчас) / 3 / 4

КРИТЕРИЙ, ОБЪЯВЛЕННЫЙ ЗАРАНЕЕ: сочетание принимается, только если
эдж над случайным входом вырос НА ОБОИХ окнах. Рост на одном —
отклоняется. Сравнение всегда против случайного входа с той же
геометрией, а не против абсолютного итога.

Это не подбор параметра, а проверка предметной гипотезы: уровень,
построенный на большей истории и большем числе касаний, надёжнее.
Если гипотеза неверна — так и запишем.
"""
from __future__ import annotations
import glob, importlib, math, os, sys
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
sys.path.insert(0, ROOT); sys.path.insert(0, f"{ROOT}/research_lab")
from research_machine import Store, ema
from random_control import sim_geo

WINDOWS = {"2024-03..2025-09": (1709251200000, 1759276800000),
           "2023-01..2024-02": (1672531200000, 1709251200000)}
SEAL = 1759276800000
MULT, HOLD, FLAT = 6.0, 336, 0.02
DRAWS = 10
LOOKBACKS = (150, 400, 800)
TOUCHES = (2, 3, 4)


def main():
    files = sorted(glob.glob(f"{DATA}/*.npz"))
    d = np.load(f"{DATA}/BTCUSDT.npz")
    c = d["ohlcv"][:, 3].astype(float); em = ema(c, 200)
    bts, bdist = d["ts"], (c - em) / em

    def flat_down(t):
        j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
        v = float(bdist[j]) if j < len(bdist) else 0.0
        return -FLAT <= v < 0

    print(f"{'глубина':<9}{'касаний':<9}{'окно':<20}{'n':>6}"
          f"{'стратегия':>12}{'случайно':>12}{'ЭДЖ':>12}{'σ':>8}")
    base = {}
    for lb in LOOKBACKS:
        for mt in TOUCHES:
            for k in list(os.environ):
                if k.startswith("HZBO1_"):
                    del os.environ[k]
            os.environ.update({
                "HZBO1_SYMBOL_ALLOWLIST": ",".join(Path(f).stem for f in files),
                "HZBO1_ALLOW_LONGS": "1", "HZBO1_ALLOW_SHORTS": "1",
                "HZBO1_SIGNAL_LOOKBACK": str(lb),
                "HZBO1_MIN_TOUCHES": str(mt),
                "HZBO1_MAX_ZONE_AGE": str(max(25, lb // 6)),
                "HZBO1_COOLDOWN_BARS_5M": "5"})
            for m in list(sys.modules):
                if m.startswith("strategies."):
                    del sys.modules[m]
            S = getattr(importlib.import_module("strategies.alt_horizontal_break_v1"),
                        "AltHorizontalBreakV1Strategy")
            real = {w: [] for w in WINDOWS}
            ctrl = {w: [[] for _ in range(DRAWS)] for w in WINDOWS}
            rng = np.random.default_rng(11)
            for fp in files:
                dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
                msk = ts < SEAL
                ts, o = ts[msk], o[msk]
                if len(ts) < lb + 300:
                    continue
                bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                        for x in range(len(ts))]
                month = (ts // (30 * 86400000)).astype(np.int64)
                st = Store(Path(fp).stem); strat = S(); block = -1
                for i in range(lb, len(bars) - 1):
                    st.rows = bars[: i + 1]; b = bars[i]
                    try:
                        s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
                    except Exception:
                        continue
                    if s is None or s.side != "short" or i <= block or not flat_down(b[0]):
                        continue
                    e0 = float(bars[i + 1][1])
                    sl = e0 + (float(s.sl) - e0) * MULT
                    risk = abs(sl - e0)
                    tps = [float(x) for x in (s.tps or [])]
                    if risk <= 0 or len(tps) < 2:
                        continue
                    sp = risk / e0
                    rr1, rr2 = abs(tps[0] - e0) / risk, abs(tps[1] - e0) / risk
                    f1 = float((s.tp_fracs or [0.5])[0])
                    r = sim_geo(bars, i, True, sp, rr1, rr2, f1, HOLD)
                    if r is None:
                        continue
                    block = i + HOLD // 4
                    for w, (a, b2) in WINDOWS.items():
                        if a <= b[0] < b2:
                            real[w].append(r)
                            pool = np.flatnonzero((month == month[i]) &
                                                  (np.arange(len(ts)) >= lb) &
                                                  (np.arange(len(ts)) < len(ts) - 1))
                            if len(pool) < 5:
                                continue
                            for dr in range(DRAWS):
                                rc = sim_geo(bars, int(rng.choice(pool)), True, sp,
                                             rr1, rr2, f1, HOLD)
                                if rc is not None:
                                    ctrl[w][dr].append(rc)
            for w in WINDOWS:
                R = np.array(real[w])
                cm = np.array([np.mean(x) for x in ctrl[w] if len(x) > 20])
                if len(R) < 50 or len(cm) < 3:
                    print(f"{lb:<9}{mt:<9}{w:<20} сделок мало"); continue
                edge = R.mean() - cm.mean()
                se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
                if lb == 150 and mt == 2:
                    base[w] = edge
                mark = ""
                if w in base:
                    dlt = edge - base[w]
                    mark = f"  {dlt:+.4f} к базе" if (lb, mt) != (150, 2) else "  БАЗА"
                print(f"{lb:<9}{mt:<9}{w:<20}{len(R):>6}{R.mean():>+11.4f}R"
                      f"{cm.mean():>+11.4f}R{edge:>+11.4f}R{edge/se:>+8.2f}{mark}", flush=True)
            print()


if __name__ == "__main__":
    main()
