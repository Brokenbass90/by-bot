"""alpaca_leverage_probe — regime-gated плечо для adaptive_v1.

Аддитивно. Переиспользует данные и логику отбора из alpaca_adaptive_backtest
(walk-forward, no look-ahead), но применяет ПЛЕЧО только когда гейт открыт (есть
позиции) и честно вычитает стоимость заёмных (margin interest) и масштабирует
издержки. Цель — ответить точно: можно ли вытянуть ~2%/мес и какой ценой по
просадке.

Caveat (тот же, что у базового бэктеста): локальный кэш ~2023-05..2026-04 —
в основном бычий, без медведя 2022. Абсолютные числа оптимистичны; ценность —
ОТНОСИТЕЛЬНЫЙ эффект плеча на доход и просадку. Медвежий год см. bakeoff.

Запуск:
    PYTHONPATH=. python3 backtest/alpaca_leverage_probe.py
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from backtest.alpaca_adaptive_backtest import load_daily, series_upto
from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP


def run_leverage(leverage: float, margin_apr: float = 0.065,
                 fee_bps_round_trip: float = 10.0, rebalance_every: int = 21,
                 cfg: Optional[AdaptiveConfig] = None) -> dict:
    cfg = cfg or AdaptiveConfig()
    data = load_daily()
    spy = data["SPY"]
    all_days = sorted(spy.keys())
    universe_syms = [s for s in data if s not in ("SPY", "QQQ", "IWM")]

    equity = 1.0
    curve: List[float] = []
    monthly = []
    start_i = 210
    i = start_i
    margin_period_cost = margin_apr * (rebalance_every / 365.0)  # на 1.0 заёмных за период
    while i < len(all_days) - rebalance_every:
        spy_closes = series_upto(spy, all_days, i)
        uni = {}
        for s in universe_syms:
            ser = series_upto(data[s], all_days, i)
            if len(ser) >= cfg.mom_slow + 2:
                uni[s] = ser
        res = select(uni, spy_closes, sectors=SECTOR_MAP, cfg=cfg)
        picks = res["picks"]
        nxt = i + rebalance_every
        gross = 0.0
        asset_ret = 0.0
        for p in picks:
            s = p["symbol"]; w = float(p["weight"])
            gross += w
            p0 = data[s].get(all_days[i]); p1 = data[s].get(all_days[nxt])
            if p0 and p1 and p0 > 0:
                asset_ret += w * (p1 / p0 - 1.0)
        # плечо: масштабируем экспозицию и доход, вычитаем стоимость заёмных + издержки
        lev_ret = leverage * asset_ret
        turnover_cost = leverage * gross * (fee_bps_round_trip / 10000.0)
        borrowed = max(0.0, leverage - 1.0) * gross   # заёмная часть только под позицией
        borrow_cost = borrowed * margin_period_cost
        period_ret = lev_ret - turnover_cost - borrow_cost
        equity *= (1.0 + period_ret)
        monthly.append(period_ret)
        curve.append(equity)
        i = nxt

    peak = -1e9; max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak if peak > 0 else 0.0)
    years = (all_days[i] - all_days[start_i]).days / 365.25
    cagr = (equity ** (1 / years) - 1.0) if years > 0 and equity > 0 else float("nan")
    pos = sum(1 for r in monthly if r > 0)
    red = sum(1 for r in monthly if r < 0)
    n = max(1, len(monthly))
    return {
        "leverage": leverage,
        "cagr_pct": cagr * 100.0,
        "avg_month_pct": (sum(monthly) / n) * 100.0,
        "max_dd_pct": max_dd * 100.0,
        "months": len(monthly),
        "red_months": red,
        "winrate_months_pct": 100.0 * pos / n,
    }


if __name__ == "__main__":
    print("=== alpaca_adaptive_v1 — regime-gated leverage (cache ~2023-05..2026-04, bull-heavy) ===")
    print(f"{'lev':>5s} {'CAGR':>7s} {'avg/mo':>7s} {'maxDD':>6s} {'win-mo':>7s} {'red':>6s}")
    print("-" * 44)
    for L in (1.0, 1.25, 1.5, 2.0):
        m = run_leverage(L)
        print(f"{m['leverage']:>5.2f} {m['cagr_pct']:>6.1f}% {m['avg_month_pct']:>6.2f}% "
              f"{m['max_dd_pct']:>5.1f}% {m['winrate_months_pct']:>6.0f}% {m['red_months']:>3d}/{m['months']}")
    print("\nМаржа 6.5%/год на заёмную часть; издержки 10bps r/t масштабируются плечом.")
    print("Помни: в медвежий год (bakeoff) база давала -6.5%/DD2.2%; плечо умножит и убыток.")
