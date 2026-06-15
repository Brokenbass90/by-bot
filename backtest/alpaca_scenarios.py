"""Scenario stress-test for alpaca_adaptive_v1 across realistic market regimes.

We lack real 2022 bear data locally, so this generates deterministic synthetic
regimes (seeded, reproducible) for the index + a correlated basket and runs the
gated selector monthly, comparing GATED vs UNGATED. The point: show how the SPY
regime gate behaves across every realistic story — and that it goes to CASH in
bear/crash regimes (avoiding the loss) while staying invested in trends.

Additive / standalone (does not touch the live bot). Run:
    PYTHONPATH=. python backtest/alpaca_scenarios.py
"""
from __future__ import annotations

import math, random
from typing import Dict, List

from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select


def _gen(kind: str, n: int = 320, seed: int = 7) -> List[float]:
    """Generate a price path for a regime. Daily steps."""
    rnd = random.Random(seed)
    p = 100.0
    out = [p]
    for i in range(1, n):
        if kind == "bull":
            drift, vol = 0.0008, 0.010
        elif kind == "bear":
            drift, vol = -0.0012, 0.014
        elif kind == "chop":
            drift, vol = 0.0, 0.009
        elif kind == "crash_recovery":
            # sharp -35% crash over ~40 bars, then recovery
            drift = -0.012 if 60 <= i < 100 else (0.0015 if i >= 100 else 0.0006)
            vol = 0.020 if 60 <= i < 110 else 0.010
        elif kind == "high_vol":
            drift, vol = 0.0003, 0.028
        else:
            drift, vol = 0.0, 0.01
        p *= (1.0 + drift + rnd.gauss(0, vol))
        out.append(max(1.0, p))
    return out


def _basket(index: List[float], k: int = 8, seed: int = 1) -> Dict[str, List[float]]:
    """Build k assets correlated to the index with idiosyncratic noise."""
    rnd = random.Random(seed)
    out = {}
    for j in range(k):
        beta = 0.7 + 0.6 * rnd.random()
        p = 100.0; series = [p]
        for i in range(1, len(index)):
            mkt = index[i] / index[i - 1] - 1.0
            p *= (1.0 + beta * mkt + rnd.gauss(0, 0.012))
            series.append(max(1.0, p))
        out[f"A{j}"] = series
    return out


def run_scenario(kind: str, use_gate: bool, fee_bps: float = 10.0,
                 rebalance_every: int = 21) -> dict:
    cfg = AdaptiveConfig()
    index = _gen(kind)
    universe_full = _basket(index)
    equity = 1.0; curve = []; monthly = []; cash_months = 0
    start = 210
    i = start
    while i < len(index) - rebalance_every:
        idx_closes = index[: i + 1]
        uni = {s: ser[: i + 1] for s, ser in universe_full.items()
               if len(ser[: i + 1]) >= cfg.mom_slow + 2}
        res = select(uni, idx_closes, cfg=cfg, force_regime_ok=(use_gate is False))
        picks = res["picks"]
        if not picks:
            cash_months += 1
        nxt = i + rebalance_every
        ret = 0.0
        for p in picks:
            s = p["symbol"]; w = float(p["weight"])
            p0 = universe_full[s][i]; p1 = universe_full[s][nxt]
            if p0 > 0:
                ret += w * (p1 / p0 - 1.0)
        ret -= sum(float(p["weight"]) for p in picks) * (fee_bps / 10000.0)
        equity *= (1.0 + ret); curve.append(equity); monthly.append(ret)
        i = nxt
    peak = -1e9; mdd = 0.0
    for v in curve:
        peak = max(peak, v); mdd = max(mdd, (peak - v) / peak if peak > 0 else 0)
    red = sum(1 for r in monthly if r < 0)
    return {"total_pct": (equity - 1) * 100, "maxDD_pct": mdd * 100,
            "red": red, "months": len(monthly), "cash_months": cash_months}


if __name__ == "__main__":
    scenarios = ["bull", "bear", "chop", "crash_recovery", "high_vol"]
    print("=== alpaca_adaptive_v1 across regimes (synthetic, seeded, with fees) ===")
    print(f"{'scenario':<16}{'GATED ret/DD/cash':<30}{'UNGATED ret/DD':<22}{'gate verdict'}")
    for sc in scenarios:
        g = run_scenario(sc, use_gate=True)
        u = run_scenario(sc, use_gate=False)
        gstr = f"{g['total_pct']:+6.1f}% DD{g['maxDD_pct']:4.1f}% cash{g['cash_months']}/{g['months']}"
        ustr = f"{u['total_pct']:+6.1f}% DD{u['maxDD_pct']:4.1f}%"
        verdict = "gate SAVES" if (u['total_pct'] < g['total_pct'] - 2 or u['maxDD_pct'] > g['maxDD_pct'] + 3) else "≈"
        print(f"{sc:<16}{gstr:<30}{ustr:<22}{verdict}")
