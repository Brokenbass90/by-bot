"""Honest maker-fill model — the missing piece of the inplay maker re-gate.

Facts so far: inplay_breakout_retest has edge (PF 1.44 taker, PF ~2.0 at maker
costs), but the naive re-gate placed a limit AT the signal close and got
0 fills — a resting limit at the last price fills only if price comes BACK.
This module models a resting limit order honestly and conservatively:

  * the order rests at `limit_price` for `validity_bars` bars after signal;
  * it fills ONLY when price trades THROUGH the limit by `through_atr * ATR`
    (a bare touch does not fill you — you are behind the queue);
  * entry price = limit price (maker), entry fee = maker_bps, no entry slippage;
  * if the FILL BAR itself would also hit the stop, the trade counts as an
    immediate SL loss (worst-case same-bar resolution, SL-first);
  * unfilled orders are recorded — an edge that never fills is not an edge.

Pure and causal; consumed by the strict re-gate runner and later by the live
pending-limit leg for parity checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from bot.market_context import atr, HIGH, LOW, CLOSE, TS

__all__ = ["LimitFill", "simulate_limit_entry", "simulate_maker_trade"]


@dataclass
class LimitFill:
    filled: bool
    fill_i: int = -1
    entry: float = float("nan")
    reason: str = ""


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except Exception:
        return float("nan")


def simulate_limit_entry(
    rows: Sequence[Sequence[float]],
    i_signal: int,
    side: str,
    limit_price: float,
    *,
    validity_bars: int = 12,
    through_atr: float = 0.05,
    atr_period: int = 14,
) -> LimitFill:
    """Rest a limit order after the signal bar; fill only on trade-through.

    Long limit below market fills when a later bar's LOW goes through
    (limit - through); short limit above market fills when HIGH goes through
    (limit + through). Conservative: the touch itself is not a fill."""
    n = len(rows)
    if not (0 <= i_signal < n - 1) or side not in ("long", "short"):
        return LimitFill(False, reason="bad_args")
    a = atr(rows[: i_signal + 1], atr_period)
    if not (a == a and a > 0) or not (limit_price == limit_price and limit_price > 0):
        return LimitFill(False, reason="no_atr_or_price")
    through = through_atr * a
    end = min(n - 1, i_signal + validity_bars)
    for j in range(i_signal + 1, end + 1):
        if side == "long":
            if _f(rows[j], LOW) <= limit_price - through:
                return LimitFill(True, fill_i=j, entry=limit_price)
        else:
            if _f(rows[j], HIGH) >= limit_price + through:
                return LimitFill(True, fill_i=j, entry=limit_price)
    return LimitFill(False, reason="expired_unfilled")


def simulate_maker_trade(
    rows: Sequence[Sequence[float]],
    i_signal: int,
    side: str,
    limit_price: float,
    *,
    sl_atr: float = 1.0,
    tp_rr: float = 2.0,
    validity_bars: int = 12,
    through_atr: float = 0.05,
    max_hold: int = 48,
    maker_fee_bps: float = 1.0,
    taker_fee_bps: float = 6.0,
    exit_slippage_bps: float = 2.0,
    atr_period: int = 14,
) -> Optional[Dict[str, Any]]:
    """Full maker trade: rest limit -> honest fill -> fixed-R exit (taker out).

    Returns None when the order never fills (caller counts unfilled-rate).
    Fees in R: maker on entry leg, taker+slippage on exit leg."""
    fill = simulate_limit_entry(
        rows, i_signal, side, limit_price,
        validity_bars=validity_bars, through_atr=through_atr, atr_period=atr_period,
    )
    if not fill.filled:
        return None
    a = atr(rows[: i_signal + 1], atr_period)
    entry = fill.entry
    if side == "long":
        stop = entry - sl_atr * a
        risk = entry - stop
        tp = entry + tp_rr * risk
    else:
        stop = entry + sl_atr * a
        risk = stop - entry
        tp = entry - tp_rr * risk
    if not (risk > 0):
        return None

    n = len(rows)
    end = min(n - 1, fill.fill_i + max_hold)
    r_gross: Optional[float] = None
    exit_i = end
    # the FILL BAR participates: if it also reaches the stop, that's an
    # immediate SL (worst case, SL-first); a same-bar TP is NOT credited.
    for j in range(fill.fill_i, end + 1):
        hi, lo = _f(rows[j], HIGH), _f(rows[j], LOW)
        if side == "long":
            if lo <= stop:
                r_gross = -1.0; exit_i = j; break
            if j > fill.fill_i and hi >= tp:
                r_gross = tp_rr; exit_i = j; break
        else:
            if hi >= stop:
                r_gross = -1.0; exit_i = j; break
            if j > fill.fill_i and lo <= tp:
                r_gross = tp_rr; exit_i = j; break
    if r_gross is None:
        c = _f(rows[exit_i], CLOSE)
        r_gross = ((c - entry) if side == "long" else (entry - c)) / risk

    risk_frac = risk / entry
    fee_r = ((maker_fee_bps + taker_fee_bps + exit_slippage_bps) / 1e4) / max(1e-9, risk_frac)
    return {
        "signal_ts": int(_f(rows[i_signal], TS)),
        "fill_ts": int(_f(rows[fill.fill_i], TS)),
        "exit_ts": int(_f(rows[exit_i], TS)),
        "side": side,
        "entry": entry,
        "r": round(r_gross - fee_r, 4),
        "wait_bars": fill.fill_i - i_signal,
    }
