"""НЕГАТИВНЫЙ КОНТРОЛЬ: сколько даёт СЛУЧАЙНЫЙ вход на наших данных.

Вопрос, на который отвечает: наш PF 1.5 — это много или обычное дело?
Без ответа мы не знаем нулевой уровень и можем принять шум за эдж.

Метод: берём те же данные, ту же геометрию выхода (стоп k*ATR, лесенка TP),
ту же частоту сделок и то же соотношение лонг/шорт — но входим в СЛУЧАЙНЫЕ
моменты. Повторяем много раз -> распределение PF под нулевой гипотезой.

Если наш реальный PF попадает внутрь этого распределения — эджа нет,
он весь в геометрии выхода, а не в выборе момента.

Запуск:
    python3 research_lab/negative_control.py SOLUSDT 64 0.578 200
    (символ, число сделок, доля лонгов, число прогонов)
"""
from __future__ import annotations

import glob
import json
import math
import os
import random
import sys


def load_bars(symbol: str, cache_dir: str = ".cache/klines") -> list:
    """Берём самый длинный кэш 5m по символу."""
    best, best_n = None, 0
    for f in glob.glob(os.path.join(cache_dir, f"{symbol}_5_*.json")):
        try:
            rows = json.load(open(f))
        except Exception:
            continue
        if len(rows) > best_n:
            best, best_n = rows, len(rows)
    return best or []


def atr(bars: list, i: int, period: int = 14) -> float:
    if i < period + 1:
        return 0.0
    s = 0.0
    for j in range(i - period + 1, i + 1):
        h, l, pc = float(bars[j][2]), float(bars[j][3]), float(bars[j - 1][4])
        s += max(h - l, abs(h - pc), abs(l - pc))
    return s / period


def simulate_one(bars: list, n_trades: int, long_frac: float, *,
                 risk_pct: float = 1.948, tp1_rr: float = 1.2, tp1_frac: float = 0.15,
                 tp2_rr: float = 2.5, max_hold: int = 2016,
                 fee_bps: float = 6.0, slip_bps: float = 2.0,
                 rng: random.Random) -> tuple[float, float, int]:
    """Один прогон случайных входов. Возвращает (PF, сумма R, число сделок).

    ВАЖНО: `risk_pct` — ширина стопа в % от цены, и она должна совпадать
    с реальной у сравниваемой стратегии. Иначе контроль нечестен: при узком
    стопе комиссия в R растёт (комиссия_R = круг / стоп) и занижает нулевой
    уровень. У ASB1 замеренная медиана = 1.948% от цены.
    """
    lo, hi = 60, len(bars) - max_hold - 2
    if hi <= lo:
        return 0.0, 0.0, 0
    gross_win = gross_loss = 0.0
    total_R = 0.0
    done = 0
    cost_R_per_side = (fee_bps + slip_bps) / 10000.0
    for _ in range(n_trades):
        i = rng.randint(lo, hi)
        entry = float(bars[i + 1][1])          # next-open, без заглядывания
        if entry <= 0:
            continue
        is_long = rng.random() < long_frac
        risk = entry * risk_pct / 100.0
        if risk <= 0:
            continue
        sl = entry - risk if is_long else entry + risk
        tp1 = entry + tp1_rr * risk * (1 if is_long else -1)
        tp2 = entry + tp2_rr * risk * (1 if is_long else -1)
        # издержки в долях R: круг = 2 стороны
        cost_R = 2.0 * cost_R_per_side * entry / risk
        realized = 0.0
        part1 = False
        for j in range(i + 1, min(i + 1 + max_hold, len(bars))):
            h, l = float(bars[j][2]), float(bars[j][3])
            if is_long:
                if l <= sl:
                    realized += (-1.0) * (1.0 - (tp1_frac if part1 else 0.0))
                    break
                if not part1 and h >= tp1:
                    realized += tp1_rr * tp1_frac
                    part1 = True
                    sl = entry               # безубыток после TP1
                if h >= tp2:
                    realized += tp2_rr * (1.0 - tp1_frac)
                    break
            else:
                if h >= sl:
                    realized += (-1.0) * (1.0 - (tp1_frac if part1 else 0.0))
                    break
                if not part1 and l <= tp1:
                    realized += tp1_rr * tp1_frac
                    part1 = True
                    sl = entry
                if l <= tp2:
                    realized += tp2_rr * (1.0 - tp1_frac)
                    break
        realized -= cost_R
        total_R += realized
        done += 1
        if realized >= 0:
            gross_win += realized
        else:
            gross_loss += -realized
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return pf, total_R, done


def run(symbol: str, n_trades: int, long_frac: float, n_runs: int = 200,
        seed: int = 12345, **kw) -> dict:
    bars = load_bars(symbol)
    if not bars:
        return {"error": f"нет кэша для {symbol}"}
    rng = random.Random(seed)
    pfs, totals = [], []
    for _ in range(n_runs):
        pf, tot, done = simulate_one(bars, n_trades, long_frac, rng=rng, **kw)
        if done >= n_trades * 0.5 and math.isfinite(pf):
            pfs.append(pf)
            totals.append(tot)
    pfs.sort()
    totals.sort()

    def q(arr, p):
        return arr[min(len(arr) - 1, int(len(arr) * p))] if arr else float("nan")

    return {
        "symbol": symbol, "bars": len(bars), "runs": len(pfs),
        "pf_median": q(pfs, 0.50), "pf_p90": q(pfs, 0.90), "pf_p95": q(pfs, 0.95),
        "pf_p99": q(pfs, 0.99), "pf_max": pfs[-1] if pfs else float("nan"),
        "R_median": q(totals, 0.50), "R_p95": q(totals, 0.95),
    }


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "SOLUSDT"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    lf = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    runs = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    r = run(sym, n, lf, runs)
    if "error" in r:
        print(r["error"])
        sys.exit(1)
    print(f"НЕГАТИВНЫЙ КОНТРОЛЬ — {r['symbol']}, {r['runs']} прогонов "
          f"по {n} случайных входов (доля лонгов {lf:.2f})")
    print(f"  баров в кэше: {r['bars']}")
    print(f"  PF под случайным входом:")
    print(f"     медиана {r['pf_median']:.3f} | p90 {r['pf_p90']:.3f} | "
          f"p95 {r['pf_p95']:.3f} | p99 {r['pf_p99']:.3f} | макс {r['pf_max']:.3f}")
    print(f"  сумма R: медиана {r['R_median']:+.1f} | p95 {r['R_p95']:+.1f}")
