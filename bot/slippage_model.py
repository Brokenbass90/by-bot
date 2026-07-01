"""Slippage calibration & honest application — close DeepSeek blind spot #1.

Backtests use a CONSTANT slippage, but real alt-coin fills in cascade/inplay moments
can slip 5-10x that. If we don't model it, a backtest looks great and live quietly
bleeds — a classic slow degradation. This module:
  * CALIBRATES realized slippage (bps) per symbol from live fills (expected vs actual);
  * ESTIMATES the bps to charge a backtest fill, scaled by notional and context
    (normal / inplay / illiquid), falling back to a CONSERVATIVE default when there's
    no live data yet;
  * APPLIES it adversely to a fill price so simulated P&L is honest.

Pure stdlib. Feed the calibration table into the WF engine so sim costs match reality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


def _pctile(xs: List[float], q: float) -> float:
    ys = sorted(xs)
    if not ys:
        return float("nan")
    i = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return ys[i]


def _median(xs: List[float]) -> float:
    return _pctile(xs, 0.5)


def fill_slippage_bps(expected_price: float, fill_price: float, side: str) -> float:
    """Adverse slippage in bps (positive = worse than expected)."""
    if not (expected_price and expected_price == expected_price):
        return float("nan")
    if side == "long":                       # bought -> adverse if filled higher
        return (fill_price - expected_price) / expected_price * 1e4
    return (expected_price - fill_price) / expected_price * 1e4   # sold -> adverse if lower


def calibrate_from_fills(fills: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build per-symbol slippage stats from live fills.

    fill = {symbol, side, expected_price, fill_price}. Returns
    {symbol: {median_bps, p90_bps, n}} using only adverse (>=0) observations clamped at 0.
    """
    buckets: Dict[str, List[float]] = {}
    for f in fills:
        sym = str(f.get("symbol", "?")).upper()
        bps = fill_slippage_bps(float(f.get("expected_price", 0) or 0),
                                float(f.get("fill_price", 0) or 0),
                                str(f.get("side", "")).lower())
        if bps == bps:
            buckets.setdefault(sym, []).append(max(0.0, bps))
    table: Dict[str, Dict[str, Any]] = {}
    for sym, xs in buckets.items():
        table[sym] = {"median_bps": round(_median(xs), 3),
                      "p90_bps": round(_pctile(xs, 0.9), 3), "n": len(xs)}
    return table


def estimate_bps(
    symbol: str,
    *,
    table: Optional[Dict[str, Dict[str, Any]]] = None,
    context: str = "normal",             # normal | inplay | illiquid
    default_bps: float = 6.0,            # conservative when uncalibrated
    inplay_mult: float = 5.0,            # DeepSeek: inplay/cascade slip 5-10x
    illiquid_mult: float = 8.0,
    min_calib_n: int = 20,
    use_p90: bool = False,               # p90 for stress/conservative sizing
    notional: Optional[float] = None,
    notional_ref: float = 500.0,         # bps roughly scales with size above this
) -> float:
    """Estimate slippage bps to charge, calibrated when possible, else conservative."""
    base = default_bps
    row = (table or {}).get(str(symbol).upper())
    if row and int(row.get("n", 0)) >= min_calib_n:
        base = float(row.get("p90_bps" if use_p90 else "median_bps", default_bps))
    mult = {"inplay": inplay_mult, "illiquid": illiquid_mult}.get(context, 1.0)
    bps = base * mult
    if notional and notional > notional_ref:
        bps *= (notional / notional_ref) ** 0.5      # sublinear size impact
    return round(bps, 3)


def apply_slippage(price: float, side: str, bps: float) -> float:
    """Return the adverse fill price after charging `bps` of slippage."""
    adj = price * (bps / 1e4)
    return price + adj if side == "long" else price - adj
