"""
Touch Quality (TQ) — Universal trendline/band touch scorer
============================================================
A "touch" is not just closeness to a line — it must show *rejection*:
price approached, tested, and bounced away. This module scores that quality.

Used by:
  - BB Mean Reversion V2+ (Bollinger band touch quality)
  - Trendline strategies (diagonal support/resistance touch quality)
  - Any horizontal S/R bounce strategy

Score: 0.0 (random noise) → 1.0 (perfect rejection candle)

Three components (weighted sum):
  1. PRECISION (40%)  — how close the bar's extreme is to the line
  2. REJECTION (40%)  — how strongly price bounced away from the touch
  3. BAR_SIZE  (20%)  — bar has meaningful range (not a doji)

Thresholds calibrated on M5 EURUSD & M5 BTC backtests:
  - min_tq=0.35 catches ~70% of V2 signals while filtering noise
  - min_tq=0.50 is strict (higher WR, fewer trades)
"""
from __future__ import annotations

from typing import List


# ─────────────────────────────────────────────────────────────────────────────
# Core scorer
# ─────────────────────────────────────────────────────────────────────────────

def touch_quality(
    bar_open: float,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    line_price: float,
    atr: float,
    is_support: bool,
    *,
    precision_atr: float = 0.30,   # extreme must be within N×ATR of line
    rejection_atr: float = 0.60,   # close must be N×ATR away from extreme
    min_bar_atr: float = 0.20,     # bar must be at least N×ATR tall
) -> float:
    """
    Score a single candle's touch of a support/resistance line.

    Parameters
    ----------
    bar_*       : OHLC of the touch candle
    line_price  : price level of the S/R or trendline at this bar
    atr         : current ATR (normalises all distances)
    is_support  : True = scoring a support touch (long setup),
                  False = scoring a resistance touch (short setup)
    precision_atr : within this many ATRs = "touched" (default 0.30)
    rejection_atr : close must be this far from the extreme (default 0.60)
    min_bar_atr : bar must have at least this range (reject dojis)

    Returns
    -------
    float in [0, 1].  Values below ~0.35 are noise.
    """
    if atr <= 0:
        return 0.0

    bar_range = bar_high - bar_low
    if bar_range < 1e-9:
        return 0.0

    if is_support:
        extreme = bar_low          # the part that touches support
        close_dist = bar_close - bar_low   # how far close is from the extreme
        prox_dist  = abs(bar_low - line_price)  # how close extreme is to line
        # wick below body (lower wick = genuine rejection)
        lower_wick = min(bar_open, bar_close) - bar_low
        wick_ratio = lower_wick / bar_range
    else:
        extreme = bar_high
        close_dist = bar_high - bar_close
        prox_dist  = abs(bar_high - line_price)
        upper_wick = bar_high - max(bar_open, bar_close)
        wick_ratio = upper_wick / bar_range

    # 1. Precision: how close the extreme is to the line
    #    Score 1.0 if on the line, 0.0 if more than precision_atr away
    precision = max(0.0, 1.0 - prox_dist / (precision_atr * atr))

    # 2. Rejection: how strongly price closed away from the extreme
    #    Score 1.0 if close is rejection_atr above/below extreme, 0 if same
    rejection = min(1.0, close_dist / (rejection_atr * atr))

    # 3. Bar size: is the bar meaningful (not a doji)?
    #    Score 1.0 if range >= min_bar_atr, 0 if tiny
    bar_size = min(1.0, bar_range / (min_bar_atr * atr))

    # Bonus: wick_ratio weight helps confirm direction
    # If wick_ratio is high (long wick = genuine test), boost rejection
    wick_boost = min(0.15, wick_ratio * 0.20)

    score = (
        0.40 * precision
        + 0.40 * rejection
        + 0.20 * bar_size
        + wick_boost
    )
    return min(1.0, max(0.0, score))


# ─────────────────────────────────────────────────────────────────────────────
# Inter-touch spacing: rejects "stacked" touches (price never left the zone)
# ─────────────────────────────────────────────────────────────────────────────

def touches_are_independent(
    touch_indices: List[int],
    min_separation: int = 5,
) -> bool:
    """
    Check that no two touches are within `min_separation` bars of each other.

    Purpose: if price hugs the band for 10 consecutive bars, that's ONE touch,
    not 10. This filter ensures each counted touch is a distinct market event.
    """
    if len(touch_indices) < 2:
        return True
    sorted_idx = sorted(touch_indices)
    for a, b in zip(sorted_idx, sorted_idx[1:]):
        if b - a < min_separation:
            return False
    return True


def weighted_touch_count(
    touch_scores: List[float],
    min_tq: float = 0.30,
) -> float:
    """
    Sum of touch scores for touches that meet the minimum threshold.
    A score of 2.0+ with min_tq=0.50 means at least 4 half-quality touches
    or 2 perfect touches — much more meaningful than raw count.
    """
    return sum(s for s in touch_scores if s >= min_tq)
