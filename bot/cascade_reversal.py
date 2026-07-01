"""Liquidation-cascade reversal detector — refined per DeepSeek H4 triggers.

Context: the existing liquidation_cascade_entry_v1 FAILED a sweep (PF 0.25) — but it
was tested on BTC/ETH (the crowded, bot-arbitraged pair DeepSeek said won't work),
in price-DROP "proxy" mode (no real liq data), and WITHOUT the full trigger stack.
This module implements the full, causal trigger set so the edge can be tested where
it might actually exist (mid-cap alts), and REJECTS the conditions that make it noise.

A cascade reversal fade fires only when ALL hold (all point-in-time, no lookahead):
  * liq-volume spike        — current bar liq volume >= `liq_pctile_min` of the last 4h;
  * open-interest flush      — OI dropped >= `oi_drop_min_pct` over the last ~15 min;
  * leverage extreme         — |funding z-score (24h)| >= `funding_z_min`;
  * timing                   — 2..`max_bars_in` bars since cascade onset (not a trend).
Side split: DOWN-cascade (longs flushed, price fell) -> LONG-only fade (revert up);
            UP-cascade (shorts squeezed, price spiked) -> SHORT-only fade.

Pairs with level_entry (stop ~1 ATR / take ~2 ATR) and decision_bus. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def _std(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _percentile_rank(value: float, sample: List[float]) -> float:
    s = [x for x in sample if x == x]
    if not s or value != value:
        return float("nan")
    return 100.0 * sum(1 for x in s if x <= value) / len(s)


@dataclass
class CascadeState:
    ok: bool
    cascade_active: bool
    direction: str            # "down" | "up" | "none"
    funding_z: float
    oi_drop_pct: float
    liq_pctile: float
    bars_since_start: int
    timing_ok: bool
    fade_side: str            # "long" | "short" | "none"
    long_ok: bool
    short_ok: bool
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _blank(reason: str) -> CascadeState:
    return CascadeState(
        ok=False, cascade_active=False, direction="none", funding_z=float("nan"),
        oi_drop_pct=float("nan"), liq_pctile=float("nan"), bars_since_start=0,
        timing_ok=False, fade_side="none", long_ok=False, short_ok=False, reason=reason,
    )


def cascade_reversal(
    price_rows: Sequence[Sequence[float]],
    funding: Sequence[float],
    open_interest: Sequence[float],
    liq_volume: Sequence[float],
    *,
    funding_window: int = 288,        # 24h of 5m bars
    funding_z_min: float = 2.0,
    oi_window: int = 3,               # ~15 min of 5m bars
    oi_drop_min_pct: float = 5.0,
    liq_lookback: int = 48,           # 4h of 5m bars
    liq_pctile_min: float = 95.0,
    onset_mult: float = 3.0,          # bar is "in cascade" if liq >= onset_mult * median baseline
    min_bars_in: int = 2,
    max_bars_in: int = 5,
    move_lookback: int = 6,           # bars to measure the cascade price move / direction
    min_move_pct: float = 2.0,
) -> CascadeState:
    """Detect an exhausted liquidation cascade and emit a one-sided fade gate."""
    n = len(price_rows)
    if n < max(move_lookback + 2, oi_window + 1) or len(liq_volume) < 5 or not funding or not open_interest:
        return _blank("insufficient_data")

    # liq-volume spike percentile (current vs last 4h)
    liq_now = _f(liq_volume[-1])
    liq_hist = [_f(x) for x in liq_volume[-liq_lookback:]]
    liq_pct = _percentile_rank(liq_now, liq_hist)

    # OI flush over the last ~15 min
    oi_now = _f(open_interest[-1])
    oi_ago = _f(open_interest[-1 - min(oi_window, len(open_interest) - 1)])
    oi_drop_pct = ((oi_ago - oi_now) / oi_ago * 100.0) if (oi_ago == oi_ago and oi_ago > 0) else float("nan")

    # funding z-score (leverage extreme)
    fwin = [_f(x) for x in funding[-funding_window:]]
    fz = ((_f(funding[-1]) - _mean(fwin)) / _std(fwin)) if _std(fwin) > 0 else 0.0

    # cascade onset: contiguous run of recent bars with liq >> baseline (median)
    _sorted = sorted(x for x in liq_hist if x == x)
    baseline = _sorted[len(_sorted) // 2] if _sorted else float("nan")
    onset_thr = onset_mult * baseline if (baseline == baseline) else float("inf")
    bars_in = 0
    for k in range(len(liq_hist) - 1, -1, -1):
        if liq_hist[k] == liq_hist[k] and liq_hist[k] >= onset_thr:
            bars_in += 1
        else:
            break

    # direction from the price move during the cascade window
    p_start = _f(price_rows[-move_lookback][OPEN])
    p_now = _f(price_rows[-1][CLOSE])
    move_pct = (p_now - p_start) / p_start * 100.0 if p_start else 0.0
    if move_pct <= -min_move_pct:
        direction = "down"
    elif move_pct >= min_move_pct:
        direction = "up"
    else:
        direction = "none"

    liq_ok = (liq_pct == liq_pct and liq_pct >= liq_pctile_min)
    oi_ok = (oi_drop_pct == oi_drop_pct and oi_drop_pct >= oi_drop_min_pct)
    funding_ok = abs(fz) >= funding_z_min
    timing_ok = (min_bars_in <= bars_in <= max_bars_in)
    cascade_active = bool(liq_ok and oi_ok and direction != "none")

    long_ok = bool(cascade_active and funding_ok and timing_ok and direction == "down")
    short_ok = bool(cascade_active and funding_ok and timing_ok and direction == "up")
    fade_side = "long" if long_ok else ("short" if short_ok else "none")

    if not cascade_active:
        reason = ("no_liq_spike" if not liq_ok else
                  "no_oi_flush" if not oi_ok else "no_directional_move")
    elif not funding_ok:
        reason = "funding_not_extreme"
    elif not timing_ok:
        reason = "cascade_too_old_or_early" if bars_in else "no_onset"
    else:
        reason = "cascade_reversal_confirmed"

    return CascadeState(
        ok=True, cascade_active=cascade_active, direction=direction, funding_z=fz,
        oi_drop_pct=oi_drop_pct, liq_pctile=liq_pct, bars_since_start=bars_in,
        timing_ok=timing_ok, fade_side=fade_side, long_ok=long_ok, short_ok=short_ok,
        reason=reason, extra={"move_pct": move_pct},
    )
