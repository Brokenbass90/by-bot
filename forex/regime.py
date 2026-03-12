from __future__ import annotations

"""
forex/regime.py — Advanced regime detection indicators.

Three complementary measures of market "ranginess" / "trendiness":

1. ChoppinessIndex(N)
   ─────────────────
   Measures how "chaotic" price action is over N bars.
   CI = 100 × log10(Σ ATR(1) / N-bar ATR) / log10(N)
   Range: 0 → 100
     < 38.2 → trending strongly
     38.2–61.8 → mild trend / transition
     > 61.8 → choppy / ranging (Fibonacci levels)
   Origin: E.W. Dreiss, 1993.

2. VolatilityPercentile(N, lookback)
   ──────────────────────────────────
   Current ATR(N) expressed as its percentile rank over the past
   `lookback` bars.  E.g. 15th percentile → market is quieter than
   85% of recent history → genuine low-volatility range.
   More robust than simple "ATR < 88% of avg" because it adapts to
   the historical distribution of volatility, not just a recent window.

3. ADXProxy(N)
   ───────────
   A lightweight ADX approximation using consecutive directional moves.
   Full ADX requires Wilder smoothing which is expensive; this proxy
   captures directional strength in O(N) without external library.
   Range: 0 → 100
     < 20 → non-trending / ranging
     20–40 → moderate trend
     > 40 → strong trend

Usage in strategies:
    from forex.regime import choppiness, volatility_percentile, adx_proxy

    ci = choppiness(candles, i, period=14)
    vp = volatility_percentile(candles, i, atr_period=14, lookback=100)
    adx = adx_proxy(candles, i, period=14)

    ranging = (ci > 61.8) and (vp < 30) and (adx < 22)
"""

from math import log10
from typing import List, Optional

from .types import Candle


# ── helpers ────────────────────────────────────────────────────────────────

def _true_range(h: float, l: float, prev_c: float) -> float:
    return max(h - l, abs(h - prev_c), abs(l - prev_c))


def _atr_simple(candles: List[Candle], start: int, end: int) -> float:
    """Simple (non-Wilder) ATR over candles[start:end]."""
    trs = []
    for i in range(max(1, start), end):
        trs.append(_true_range(candles[i].h, candles[i].l, candles[i - 1].c))
    if not trs:
        return float("nan")
    return sum(trs) / len(trs)


# ── Choppiness Index ────────────────────────────────────────────────────────

def choppiness(candles: List[Candle], i: int, period: int = 14) -> float:
    """Choppiness Index over the last `period` candles ending at index i.

    Returns float in ~[0, 100]:
      > 61.8  → ranging / choppy
      < 38.2  → trending
    Returns nan if insufficient data.
    """
    if i < period or period < 2:
        return float("nan")

    start = i - period
    end = i + 1  # inclusive

    # Sum of ATR(1) bars (individual true ranges)
    sum_tr = 0.0
    for j in range(start + 1, end):
        sum_tr += _true_range(candles[j].h, candles[j].l, candles[j - 1].c)

    # N-period range (highest high − lowest low)
    rng_high = max(c.h for c in candles[start:end])
    rng_low  = min(c.l for c in candles[start:end])
    rng = rng_high - rng_low

    if rng <= 0 or sum_tr <= 0:
        return float("nan")

    return 100.0 * log10(sum_tr / rng) / log10(period)


# ── Volatility Percentile ───────────────────────────────────────────────────

def volatility_percentile(
    candles: List[Candle],
    i: int,
    atr_period: int = 14,
    lookback: int = 100,
) -> float:
    """Percentile rank of current ATR(atr_period) vs past `lookback` readings.

    Returns 0–100:
      0  → ATR at all-time low for this lookback → extremely quiet
      50 → ATR at median of recent history
      100 → ATR at all-time high → extremely volatile

    Returns nan if insufficient data.
    """
    need = atr_period + lookback + 2
    if i < need:
        return float("nan")

    # Collect ATR values: one per bar over the lookback window
    atr_hist: List[float] = []
    step = max(1, lookback // 20)  # ~20 samples for speed
    for k in range(i - lookback, i, step):
        if k < atr_period:
            continue
        a = _atr_simple(candles, k - atr_period, k + 1)
        if a == a and a > 0:
            atr_hist.append(a)

    if len(atr_hist) < 3:
        return float("nan")

    # Current ATR
    cur_atr = _atr_simple(candles, i - atr_period, i + 1)
    if not (cur_atr == cur_atr and cur_atr > 0):
        return float("nan")

    below = sum(1 for v in atr_hist if v < cur_atr)
    return 100.0 * below / len(atr_hist)


# ── ADX Proxy ───────────────────────────────────────────────────────────────

def adx_proxy(candles: List[Candle], i: int, period: int = 14) -> float:
    """Lightweight ADX proxy: measures directional bias without Wilder smoothing.

    Algorithm:
      +DM = max(High − prevHigh, 0) if > |Low − prevLow|  else 0
      −DM = max(prevLow − Low,   0) if > |High − prevHigh| else 0
      DX  = 100 × |+DM_sum − −DM_sum| / (+DM_sum + −DM_sum + ε)
    Returns 0–100; lower = more ranging.

    Returns nan if insufficient data.
    """
    if i < period + 1:
        return float("nan")

    plus_dm_sum = 0.0
    minus_dm_sum = 0.0

    for j in range(i - period + 1, i + 1):
        up   = candles[j].h - candles[j - 1].h
        down = candles[j - 1].l - candles[j].l
        if up > 0 and up > down:
            plus_dm_sum += up
        elif down > 0 and down > up:
            minus_dm_sum += down

    denom = plus_dm_sum + minus_dm_sum
    if denom <= 0:
        return 0.0
    return 100.0 * abs(plus_dm_sum - minus_dm_sum) / denom


# ── Composite flat-market score ─────────────────────────────────────────────

def is_ranging(
    candles: List[Candle],
    i: int,
    ci_threshold: float = 58.0,
    vp_threshold: float = 40.0,
    adx_threshold: float = 25.0,
    ci_period: int = 14,
    atr_period: int = 14,
    vp_lookback: int = 100,
    adx_period: int = 14,
    require_all: bool = False,
) -> Optional[bool]:
    """Returns True if market is ranging, False if trending, None if insufficient data.

    By default, 2-of-3 vote (require_all=False):
      - CI > ci_threshold  (choppy)
      - VP < vp_threshold  (quiet volatility for this pair)
      - ADX < adx_threshold (no directional momentum)
    """
    ci  = choppiness(candles, i, ci_period)
    vp  = volatility_percentile(candles, i, atr_period, vp_lookback)
    adx = adx_proxy(candles, i, adx_period)

    scores = []
    if ci == ci:
        scores.append(ci > ci_threshold)
    if vp == vp:
        scores.append(vp < vp_threshold)
    if adx == adx:
        scores.append(adx < adx_threshold)

    if len(scores) < 2:
        return None

    if require_all:
        return all(scores)
    return sum(scores) >= 2  # majority vote
