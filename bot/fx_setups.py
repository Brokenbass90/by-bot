"""FX/CFD native setups — structural edges we can sweep by the thousands.

NOT a port of crypto legs. These are FX/gold structural patterns, each composed from
our existing tech so they inherit honest levels/execution/side-split and plug into the
same preflight -> OOS gate. Every setup is parameter-rich for wide sweeps (session
windows, tolerances, TP_RR, quality). Row [ts(sec),o,h,l,c,v]; ts drives session logic.

Setups:
  1. session_range_fade   — fade the extreme of the (Asian/prior) session range.
  2. round_level_sweep    — stop-hunt reversal at a round/session level (XAU/FX desks).
  3. session_breakout_retest — London/NY break of prior session range + clean retest.
  4. trend_pullback       — pullback to a level WITH the elder tide.

All emit one-directional gates (long_ok XOR short_ok) + level + reason. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import atr, horizontal_levels, CLOSE, HIGH, LOW, OPEN
from bot.range_filter import range_state
from bot.liquidity_sweep import liquidity_sweep
from bot.breakout_confirm import breakout_confirm
from bot.retest_quality import best_retest, score_retest
from bot.elder_filter import elder_bias
from bot.news_session_filter import entry_allowed, session_of
from bot.unified_levels import _round_levels


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


@dataclass
class FxSignal:
    setup: str
    long_ok: bool
    short_ok: bool
    side: str                 # "long" | "short" | "none"
    level: float
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _none(setup: str, reason: str) -> FxSignal:
    return FxSignal(setup, False, False, "none", float("nan"), reason)


def _news_ok(ts, events, price, block_asia) -> bool:
    fs = entry_allowed(ts, events=events, price=price, avoid_low_liq_session=block_asia)
    return fs.allow


def session_range_fade(
    rows: Sequence[Sequence[float]], *,
    events=None, block_asia: bool = True, edge_zone: float = 0.20,
    require_range: bool = True,
) -> FxSignal:
    """Fade the extreme of a confirmed session range (short top / long bottom)."""
    if len(rows) < 40:
        return _none("session_range_fade", "insufficient_data")
    ts = _f(rows[-1], 0); price = _f(rows[-1], CLOSE)
    if not _news_ok(ts, events, price, block_asia):
        return _none("session_range_fade", "news_or_session_block")
    rs = range_state(rows, lower_zone=edge_zone, upper_zone=1 - edge_zone)
    if require_range and not (rs.ok and rs.is_range):
        return _none("session_range_fade", "not_range")
    if rs.short_ok:
        return FxSignal("session_range_fade", False, True, "short", rs.upper_now, "fade_top")
    if rs.long_ok:
        return FxSignal("session_range_fade", True, False, "long", rs.lower_now, "fade_bottom")
    return _none("session_range_fade", rs.reason)


def round_level_sweep(
    rows: Sequence[Sequence[float]], *,
    events=None, block_asia: bool = True, tol_frac: float = 0.0006,
    atr_value: Optional[float] = None,
) -> FxSignal:
    """Stop-hunt reversal: liquidity swept AT/near a round level -> fade back."""
    if len(rows) < 30:
        return _none("round_level_sweep", "insufficient_data")
    ts = _f(rows[-1], 0); price = _f(rows[-1], CLOSE)
    if not _news_ok(ts, events, price, block_asia):
        return _none("round_level_sweep", "news_or_session_block")
    sw = liquidity_sweep(rows, atr_value=atr_value)
    if sw.event != "sweep_reversal":
        return _none("round_level_sweep", sw.reason)
    # the swept pool must sit near a round level (desk stop-hunt signature)
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    rounds = _round_levels(price, a) if (a == a and a > 0) else []
    near_round = any(abs(sw.pool_level - r) <= tol_frac * price for r in rounds)
    if not near_round:
        return _none("round_level_sweep", "pool_not_round")
    return FxSignal("round_level_sweep", sw.long_ok, sw.short_ok, sw.side, sw.pool_level,
                    "round_stop_hunt")


def session_breakout_retest(
    rows: Sequence[Sequence[float]], *,
    events=None, sessions=("london", "london_ny_overlap", "newyork"),
    level_lookback: int = 120,
) -> FxSignal:
    """Break of prior range in an active session, then a clean retest of the level."""
    if len(rows) < 40:
        return _none("session_breakout_retest", "insufficient_data")
    ts = _f(rows[-1], 0); price = _f(rows[-1], CLOSE)
    if session_of(ts) not in sessions:
        return _none("session_breakout_retest", "wrong_session")
    if not _news_ok(ts, events, price, False):
        return _none("session_breakout_retest", "news_block")
    # Bound every geometry calculation to a causal rolling window.  Passing the
    # whole growing prefix makes walk-forward research O(n²) and lets ancient
    # levels leak into a setup that is explicitly session-local.
    window = list(rows[-max(60, int(level_lookback)):])
    bo = breakout_confirm(window)
    if not bo.confirmed:
        return _none("session_breakout_retest", bo.reason)
    if bo.kind != "horizontal":
        # score_retest expects touch/freshness metadata for a concrete level.
        # A projected channel value has different geometry and needs its own
        # sloped-retest contract; pretending it is a horizontal level produces
        # a misleading quality score.
        return _none("session_breakout_retest", "sloped_retest_metadata_unavailable")
    side = "support" if bo.direction == "up" else "resistance"
    source_side = "resistance" if bo.direction == "up" else "support"
    a = float((bo.extra or {}).get("atr") or atr(window))
    source_levels = horizontal_levels(window, side=source_side, atr_value=a, min_touches=2)
    source = min(source_levels, key=lambda lv: abs(float(lv["level"]) - float(bo.level))) if source_levels else None
    if source is None:
        return _none("session_breakout_retest", "broken_level_metadata_unavailable")
    rq = score_retest(
        window,
        bo.level,
        side,
        atr_value=a,
        last_touch_idx=source.get("last_idx"),
        touches=int(source.get("touches", 0)),
    )
    if not rq.entry_ok:
        return _none("session_breakout_retest", f"retest_{rq.reason}")
    return FxSignal("session_breakout_retest", rq.long_ok, rq.short_ok, rq.side, bo.level,
                    f"break_{bo.direction}_retest")


def trend_pullback(
    rows: Sequence[Sequence[float]], *, events=None, min_quality: float = 0.55,
    level_lookback: int = 240,
) -> FxSignal:
    """Pullback to a level WITH the elder tide (long in uptide / short in downtide)."""
    if len(rows) < 60:
        return _none("trend_pullback", "insufficient_data")
    ts = _f(rows[-1], 0); price = _f(rows[-1], CLOSE)
    if not _news_ok(ts, events, price, False):
        return _none("trend_pullback", "news_block")
    # 240 H1 bars preserve the slow Elder tide while keeping walk-forward work
    # bounded.  The setup remains causal and no longer rescans years of history
    # for every new bar.
    window = list(rows[-max(60, int(level_lookback)):])
    eb = elder_bias(window)
    if eb.tide == "up":
        rq = best_retest(window, min_quality=min_quality)
        if rq.entry_ok and eb.allow_long:
            if rq.side == "long":
                return FxSignal("trend_pullback", True, False, "long", rq.level, "pullback_uptide")
    elif eb.tide == "down":
        rq = best_retest(window, min_quality=min_quality)
        if rq.entry_ok and eb.allow_short:
            if rq.side == "short":
                return FxSignal("trend_pullback", False, True, "short", rq.level, "pullback_downtide")
    return _none("trend_pullback", f"tide_{eb.tide}_no_setup")
