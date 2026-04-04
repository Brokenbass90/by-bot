"""
strategy_scorer.py — Per-strategy coin fitness scoring based on current price state.

Each strategy family needs coins that are in a specific price state RIGHT NOW,
not just coins that were historically volatile. This module scores each candidate
coin 0.0–1.0 based on how well its current price structure matches what each
strategy needs to generate signals.

Scoring logic by strategy env_key prefix:
  ARF1      → coin near N-day HIGH + RSI elevated + low ER (ranging)
  ASB1      → coin near N-day LOW  + RSI depressed + low ER (ranging)
  BREAKDOWN → coin at/below recent lows + negative momentum + low RSI
  BREAKDOWN2 → same as BREAKDOWN (1h structure variant)
  ASC1      → high R² on linear regression (clean channel) + moderate ER
  ARS1      → low ER (range-bound) + moderate Bollinger Band width
  PF2       → recent large pump/dump move detected + RSI extreme
  ETS2      → high ER (trending) + EMA alignment confirms direction
  BREAKOUT  → coin near N-day HIGH + positive momentum + high ER

Returns 0.5 (neutral) for unknown strategy keys or insufficient data.

Integration:
    from scripts.strategy_scorer import score_for_strategy
    fit = score_for_strategy(env_key, closes_1h, highs_1h, lows_1h)
    # combine with market_score: total = market_score * 0.4 + fit * 0.6
"""

from __future__ import annotations

import math
from typing import List


# ---------------------------------------------------------------------------
# Indicator helpers (self-contained, no external deps)
# ---------------------------------------------------------------------------

def _rsi(closes: List[float], period: int = 14) -> float:
    if period <= 0 or len(closes) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses < 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _efficiency_ratio(closes: List[float], period: int = 20) -> float:
    """Kaufman Efficiency Ratio: 0 = pure noise/range, 1 = straight trend."""
    if len(closes) < period + 1:
        return 0.5
    net = abs(closes[-1] - closes[-(period + 1)])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - period, len(closes)))
    return net / path if path > 1e-12 else 0.0


def _position_in_range(closes: List[float], highs: List[float], lows: List[float],
                        lookback: int = 72) -> float:
    """
    Where is the current price in its recent range?
    Returns 0.0 = at the bottom, 1.0 = at the top.
    Uses actual highs/lows (not just closes) for a more accurate range.
    """
    h = highs[-lookback:] if len(highs) >= lookback else highs
    l = lows[-lookback:] if len(lows) >= lookback else lows
    hi = max(h) if h else closes[-1]
    lo = min(l) if l else closes[-1]
    rng = hi - lo
    if rng < 1e-12:
        return 0.5
    return max(0.0, min(1.0, (closes[-1] - lo) / rng))


def _momentum_pct(closes: List[float], bars_ago: int = 5) -> float:
    """Simple momentum: (cur - N bars ago) / N bars ago. Positive = up, negative = down."""
    if len(closes) < bars_ago + 1:
        return 0.0
    ref = closes[-(bars_ago + 1)]
    if abs(ref) < 1e-12:
        return 0.0
    return (closes[-1] - ref) / abs(ref)


def _max_move_pct(closes: List[float], window: int = 12) -> float:
    """Largest single-window % move in the entire history. Used for pump/dump detection."""
    if len(closes) < window + 1:
        return 0.0
    best = 0.0
    for i in range(window, len(closes)):
        ref = closes[i - window]
        if abs(ref) < 1e-12:
            continue
        move = abs((closes[i] - ref) / ref)
        if move > best:
            best = move
    return best


def _linear_r2(closes: List[float]) -> float:
    """R² of a linear regression on the close series. 1.0 = perfect line, 0.0 = chaos."""
    n = len(closes)
    if n < 5:
        return 0.0
    xs = list(range(n))
    xm = (n - 1) / 2.0
    ym = sum(closes) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, closes))
    den = sum((x - xm) ** 2 for x in xs)
    if den < 1e-12:
        return 0.0
    m = num / den
    b = ym - m * xm
    ss_res = sum((y - (m * x + b)) ** 2 for x, y in zip(xs, closes))
    ss_tot = sum((y - ym) ** 2 for y in closes)
    if ss_tot < 1e-12:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _bb_width_pct(closes: List[float], period: int = 20, std_mult: float = 2.0) -> float:
    """Bollinger Band width as % of price. 0 = squeezed, high = expanded."""
    if len(closes) < period:
        return 0.0
    win = closes[-period:]
    mean = sum(win) / period
    if mean < 1e-12:
        return 0.0
    var = sum((c - mean) ** 2 for c in win) / period
    std = math.sqrt(max(var, 0.0))
    return (2.0 * std_mult * std) / mean * 100.0


# ---------------------------------------------------------------------------
# Per-strategy scoring
# ---------------------------------------------------------------------------

def score_for_strategy(
    env_key: str,
    closes: List[float],
    highs: List[float],
    lows: List[float],
) -> float:
    """
    Score a coin for a specific strategy family.

    Parameters
    ----------
    env_key : str
        The strategy's env key, e.g. "ARF1_SYMBOL_ALLOWLIST".
    closes   : list of float — 1h close prices, oldest first
    highs    : list of float — 1h highs, oldest first
    lows     : list of float — 1h lows, oldest first

    Returns
    -------
    float in [0.0, 1.0] — 1.0 = ideal fit, 0.5 = neutral, 0.0 = wrong state
    """
    ek = env_key.upper()

    if len(closes) < 20:
        return 0.5  # insufficient data → neutral

    rsi    = _rsi(closes, 14)
    er     = _efficiency_ratio(closes, 20)
    pos    = _position_in_range(closes, highs, lows, lookback=72)

    rsi_ok = math.isfinite(rsi)

    # ── ARF1: Resistance fade (short at top of range) ───────────────────────
    if "ARF1" in ek:
        pos_score = pos                                           # 1 = at top = perfect
        rsi_score = max(0.0, (rsi - 50.0) / 50.0) if rsi_ok else 0.5   # elevated RSI
        er_score  = max(0.0, 1.0 - er / 0.5)                   # low ER = ranging
        return round(pos_score * 0.50 + rsi_score * 0.30 + er_score * 0.20, 4)

    # ── ASB1: Support bounce (long at bottom of range) ──────────────────────
    if "ASB1" in ek:
        pos_score = 1.0 - pos                                    # 1 = at bottom = perfect
        rsi_score = max(0.0, (50.0 - rsi) / 50.0) if rsi_ok else 0.5   # depressed RSI
        er_score  = max(0.0, 1.0 - er / 0.5)                   # low ER = ranging
        return round(pos_score * 0.50 + rsi_score * 0.30 + er_score * 0.20, 4)

    # ── BREAKDOWN / BREAKDOWN2: Short breakdown below support ────────────────
    if "BREAKDOWN" in ek:
        pos_score  = 1.0 - pos                                   # 1 = at lows = perfect
        mom        = _momentum_pct(closes, bars_ago=5)
        mom_score  = max(0.0, min(1.0, -mom * 8.0))             # negative momentum
        rsi_score  = max(0.0, (50.0 - rsi) / 50.0) if rsi_ok else 0.5
        return round(pos_score * 0.40 + mom_score * 0.35 + rsi_score * 0.25, 4)

    # ── ASC1: Sloped channel mean reversion ─────────────────────────────────
    if "ASC1" in ek:
        # Use last 72 bars (3 days on 1h) for channel quality
        r2 = _linear_r2(closes[-72:] if len(closes) >= 72 else closes)
        r2_score  = r2                                           # higher = cleaner channel
        # Moderate ER preferred: 0.15-0.45 ideal (some slope but not runaway)
        er_ideal  = 0.30
        er_score  = max(0.0, 1.0 - abs(er - er_ideal) / 0.35)
        return round(r2_score * 0.60 + er_score * 0.40, 4)

    # ── ARS1: Bollinger Band range scalper ───────────────────────────────────
    if "ARS1" in ek:
        er_score  = max(0.0, 1.0 - er / 0.35)                  # low ER = ranging
        bb        = _bb_width_pct(closes, 20, 2.0)
        # Ideal BB width 3-12%: score peaks at 6%, falls off outside this range
        bb_score  = max(0.0, 1.0 - abs(bb - 6.0) / 8.0)
        return round(er_score * 0.55 + bb_score * 0.45, 4)

    # ── AVW1: VWAP mean reversion / intraday stretch fade ──────────────────
    if "AVW1" in ek:
        er_score = max(0.0, 1.0 - er / 0.38)                  # wants chop / inefficiency
        edge_score = min(1.0, abs(pos - 0.5) * 2.0)          # best near range extremes
        rsi_extreme = abs(rsi - 50.0) / 50.0 if rsi_ok else 0.3
        return round(er_score * 0.45 + edge_score * 0.35 + rsi_extreme * 0.20, 4)

    # ── PF2: Pump/dump fade ─────────────────────────────────────────────────
    if "PF2" in ek:
        # Check for a recent large move (>5% in any 12-bar window)
        max_move  = _max_move_pct(closes, window=12)
        move_score = min(1.0, max_move / 0.08)                  # 8% move = score 1.0
        rsi_extreme = abs(rsi - 50.0) / 50.0 if rsi_ok else 0.0  # far from 50 = good
        return round(move_score * 0.60 + rsi_extreme * 0.40, 4)

    # ── ETS2: Elder Triple Screen (trend following) ─────────────────────────
    if "ETS2" in ek:
        er_score  = min(1.0, er / 0.45)                         # high ER = trending
        ema13     = _ema(closes, 13)
        ema34     = _ema(closes, 34)
        # Bonus if EMAs agree on direction (13 above or below 34)
        if math.isfinite(ema13) and math.isfinite(ema34) and abs(ema13 - ema34) > 1e-9:
            ema_aligned = 1.0
        else:
            ema_aligned = 0.3
        return round(er_score * 0.60 + ema_aligned * 0.40, 4)

    # ── BREAKOUT: Bullish price breakout ────────────────────────────────────
    if "BREAKOUT" in ek:
        pos_score = pos                                          # near high = good
        mom       = _momentum_pct(closes, bars_ago=5)
        mom_score = max(0.0, min(1.0, mom * 8.0))              # positive momentum
        er_score  = min(1.0, er / 0.45)                         # trending = good
        return round(pos_score * 0.40 + mom_score * 0.35 + er_score * 0.25, 4)

    # ── Unknown strategy → neutral ───────────────────────────────────────────
    return 0.5


# ---------------------------------------------------------------------------
# Convenience: human-readable breakdown for logging
# ---------------------------------------------------------------------------

def explain_score(
    env_key: str,
    closes: List[float],
    highs: List[float],
    lows: List[float],
) -> str:
    """Return a one-line explanation of the strategy fit score components."""
    ek = env_key.upper()
    if len(closes) < 20:
        return "insufficient_data"

    rsi = _rsi(closes, 14)
    er  = _efficiency_ratio(closes, 20)
    pos = _position_in_range(closes, highs, lows, lookback=72)
    total = score_for_strategy(env_key, closes, highs, lows)

    parts = [f"score={total:.3f}"]
    parts.append(f"pos={pos:.2f}")
    parts.append(f"er={er:.2f}")
    if math.isfinite(rsi):
        parts.append(f"rsi={rsi:.1f}")

    if "ASC1" in ek:
        r2 = _linear_r2(closes[-72:] if len(closes) >= 72 else closes)
        parts.append(f"r2={r2:.2f}")
    if "ARS1" in ek:
        bb = _bb_width_pct(closes, 20, 2.0)
        parts.append(f"bb_w={bb:.1f}%")
    if "AVW1" in ek:
        parts.append(f"edge={abs(pos - 0.5) * 2.0:.2f}")
    if "PF2" in ek:
        mv = _max_move_pct(closes, window=12)
        parts.append(f"max_move={mv*100:.1f}%")

    return " | ".join(parts)
