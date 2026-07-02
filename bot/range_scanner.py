"""Range-quality scanner — pick the RIGHT instruments for a grid / range legs.

A grid only earns on instruments that are genuinely ranging AND stay ranging. The
missing piece behind the grid's losses was instrument selection: gridding a coin that
is actually trending = death. This scans a universe and ranks each instrument by
range-quality so smart_grid / range-fade legs run ONLY on the best flats.

Score blends (all from our tech, causal):
  * range confirmation (range_filter is_range + 3-measure votes);
  * flat regime probability (regime_hmm) and NOT high_vol;
  * channel width in a tradeable band (wide enough to grid, not exploding);
  * penalty for trend (|elder tide| via slope).

Universe = {symbol: rows[[ts,o,h,l,c,v]...]}. Pure stdlib. Feeds smart_grid/FX/range legs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import atr, classify_channel
from bot.range_filter import range_state
from bot.regime_hmm import regime_probs


@dataclass
class RangeScore:
    symbol: str
    score: float                 # 0..1 range-quality
    is_range: bool
    votes: int
    regime: str
    range_prob: float
    width_atr: float
    tradeable: bool              # passes min bar for gridding
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def score_instrument(
    symbol: str,
    rows: Sequence[Sequence[float]],
    *,
    lookback: int = 60,
    min_width_atr: float = 2.0,
    max_width_atr: float = 12.0,
    min_score: float = 0.5,
) -> RangeScore:
    """Grade one instrument's range-quality for gridding/range trading."""
    if len(rows) < max(lookback, 40):
        return RangeScore(symbol, 0.0, False, 0, "unknown", 0.0, float("nan"), False, "insufficient_data")
    a = atr(rows)
    if not (a == a and a > 0):
        return RangeScore(symbol, 0.0, False, 0, "unknown", 0.0, float("nan"), False, "no_atr")
    ch = classify_channel(rows, atr_value=a, lookback=lookback)
    lo, up = ch.get("lower_now", float("nan")), ch.get("upper_now", float("nan"))
    width_atr = ((up - lo) / a) if (lo == lo and up == up and up > lo) else 0.0

    rs = range_state(rows)
    reg = regime_probs(rows)
    range_prob = reg.probs.get("range", 0.0) if reg.ok else 0.0

    vote_score = (rs.votes / 3.0) if rs.ok else 0.0                     # 0..1
    range_conf = 1.0 if (rs.ok and rs.is_range) else 0.0
    regime_score = range_prob if reg.dominant != "high_vol" else 0.0    # flat/range good, chaos bad
    # width in band -> best score at mid-band, 0 outside
    if min_width_atr <= width_atr <= max_width_atr:
        width_score = 1.0
    else:
        width_score = 0.0
    slope_penalty = 0.0
    if reg.ok and reg.dominant in ("bull", "bear"):
        slope_penalty = 0.3 * reg.confidence                            # trending -> penalize grid

    score = max(0.0, 0.30 * range_conf + 0.25 * vote_score + 0.25 * regime_score
                + 0.20 * width_score - slope_penalty)
    tradeable = bool(rs.ok and rs.is_range and (min_width_atr <= width_atr <= max_width_atr)
                     and reg.dominant != "high_vol" and score >= min_score)
    return RangeScore(symbol, round(score, 4), bool(rs.ok and rs.is_range),
                      rs.votes if rs.ok else 0, reg.dominant if reg.ok else "unknown",
                      round(range_prob, 3), round(width_atr, 2), tradeable,
                      "ok" if tradeable else "below_bar")


def scan(universe: Dict[str, Sequence[Sequence[float]]], **kw) -> List[RangeScore]:
    """Score every instrument; return ranked best-first."""
    out = [score_instrument(sym, rows, **kw) for sym, rows in universe.items()]
    out.sort(key=lambda r: (r.tradeable, r.score), reverse=True)
    return out


def best_ranging(universe: Dict[str, Sequence[Sequence[float]]], *, top_n: int = 5, **kw) -> List[str]:
    """Symbols of the top tradeable ranging instruments (for the grid to run on)."""
    return [r.symbol for r in scan(universe, **kw) if r.tradeable][:top_n]
