"""Monthly-rebalance backtest for alpaca_adaptive_v1 over the local equity cache.

Honest by construction:
  * walk-forward monthly rebalance (no look-ahead: picks use data up to t only),
  * reports CAGR, max drawdown, % positive months, # red months, trades,
  * supports A/B toggles: regime gate ON/OFF and an optional AI-approval filter,
    so we can MEASURE what each contributes (this is how you test the AI filter).

Caveat: the local cache is ~2023-05..2026-04 (mostly bull, no 2022 bear), so
absolute returns are optimistic — the value here is the *relative* A/B deltas
and that the gate steps aside in real drawdowns. A true bear-inclusive WF needs
the 2022 data feed.
"""
from __future__ import annotations

import csv, datetime as dt, glob, math, os
from typing import Dict, List, Optional

from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

DATA = "data_cache/equities_1h"


def load_daily() -> Dict[str, Dict[dt.date, float]]:
    out = {}
    for f in glob.glob(os.path.join(DATA, "*_M5.csv")):
        sym = os.path.basename(f).replace("_M5.csv", "")
        daily = {}
        for row in csv.reader(open(f)):
            if row[0] == "ts":
                continue
            d = dt.datetime.utcfromtimestamp(int(row[0])).date()
            daily[d] = float(row[4])
        out[sym] = daily
    return out


def series_upto(daily: Dict[dt.date, float], days: List[dt.date], upto_idx: int) -> List[float]:
    return [daily[d] for d in days[: upto_idx + 1] if d in daily]


def run(use_gate: bool, ai_approver=None, cfg: Optional[AdaptiveConfig] = None,
        fee_bps_round_trip: float = 10.0, rebalance_every: int = 21) -> dict:
    cfg = cfg or AdaptiveConfig()
    data = load_daily()
    spy = data["SPY"]
    all_days = sorted(spy.keys())
    # universe = non-ETF symbols
    universe_syms = [s for s in data if s not in ("SPY", "QQQ", "IWM")]

    equity = 1.0
    curve = []
    monthly_returns = []
    trades = 0
    start_i = 210  # need >=200 for the 200d gate + lookbacks

    i = start_i
    while i < len(all_days) - rebalance_every:
        day = all_days[i]
        spy_closes = series_upto(spy, all_days, i)
        uni = {}
        for s in universe_syms:
            ser = series_upto(data[s], all_days, i)
            if len(ser) >= cfg.mom_slow + 2:
                uni[s] = ser
        res = select(uni, spy_closes, sectors=SECTOR_MAP, cfg=cfg,
                     ai_approver=ai_approver, force_regime_ok=use_gate is False)
        picks = res["picks"]
        # forward return over the holding window
        nxt = i + rebalance_every
        period_ret = 0.0
        if picks:
            trades += len(picks)
            for p in picks:
                s = p["symbol"]; w = float(p["weight"])
                p0 = data[s].get(all_days[i]); p1 = data[s].get(all_days[nxt])
                if p0 and p1 and p0 > 0:
                    period_ret += w * (p1 / p0 - 1.0)
        # transaction cost: round-trip per held weight each rebalance (slippage/spread;
        # Alpaca is commission-free but spread/slippage is real). Conservative.
        turnover_cost = sum(float(p["weight"]) for p in picks) * (fee_bps_round_trip / 10000.0)
        period_ret -= turnover_cost
        # else: cash -> 0% for the month
        equity *= (1.0 + period_ret)
        monthly_returns.append(period_ret)
        curve.append(equity)
        i = nxt

    # metrics
    peak = -1e9; max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak if peak > 0 else 0.0)
    years = (all_days[i] - all_days[start_i]).days / 365.25
    cagr = (equity ** (1 / years) - 1.0) if years > 0 and equity > 0 else float("nan")
    pos = sum(1 for r in monthly_returns if r > 0)
    red = sum(1 for r in monthly_returns if r < 0)
    return {
        "total_return_pct": (equity - 1.0) * 100.0,
        "cagr_pct": cagr * 100.0,
        "max_dd_pct": max_dd * 100.0,
        "months": len(monthly_returns),
        "pos_months": pos, "red_months": red,
        "winrate_months_pct": 100.0 * pos / max(1, len(monthly_returns)),
        "avg_trades_per_rebalance": trades / max(1, len(monthly_returns)),
    }


def _fmt(label, m):
    return (f"{label:<28} ret={m['total_return_pct']:+6.1f}% CAGR={m['cagr_pct']:+5.1f}% "
            f"maxDD={m['max_dd_pct']:4.1f}% winMonths={m['winrate_months_pct']:4.0f}% "
            f"red={m['red_months']:2d}/{m['months']} pos={m['pos_months']}")


def _chase_filter(symbol, metrics):
    # toy AI-style filter: veto "chasing" — extremely hot short-term momentum
    return (metrics.get("mom_fast", 0.0) <= 0.25, "ai_avoid_overbought_chase")


if __name__ == "__main__":
    gated = run(use_gate=True)
    ungated = run(use_gate=False)
    gated_ai = run(use_gate=True, ai_approver=_chase_filter)
    gated_nofee = run(use_gate=True, fee_bps_round_trip=0.0)
    print("=== alpaca_adaptive_v1 backtest (local cache ~2023-05..2026-04) ===")
    print(_fmt("GATED (regime ON)", gated))
    print(_fmt("UNGATED (regime OFF)", ungated))
    print(_fmt("GATED + AI filter", gated_ai))
    print(_fmt("GATED (no fees, ref)", gated_nofee))
    print()
    print(f"Fee drag (10bps r/t):  CAGR {gated_nofee['cagr_pct']:+.1f}% -> {gated['cagr_pct']:+.1f}%")
    print(f"Gate effect on maxDD:  {ungated['max_dd_pct']:.1f}% -> {gated['max_dd_pct']:.1f}%")
    print(f"AI filter effect:      red months {gated['red_months']} -> {gated_ai['red_months']}, "
          f"CAGR {gated['cagr_pct']:+.1f}% -> {gated_ai['cagr_pct']:+.1f}%")
