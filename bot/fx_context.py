"""One bounded, causal context builder for FX/CFD V2 consumers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from bot.elder_filter import elder_bias
from bot.fx_calendar import session_labels
from bot.fx_contracts import FxContext, FxInstrumentSpec
from bot.fx_instruments import instrument_round_levels
from bot.market_context import CLOSE, TS, atr
from bot.news_session_filter import entry_allowed
from bot.range_filter import range_state
from bot.regime_hmm import regime_probs
from bot.unified_levels import unified_levels


def build_fx_context(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    events: Optional[Sequence[Dict[str, Any]]] = None,
    lookback: int = 240,
    avoid_low_liquidity: bool = True,
    bar_seconds: int = 3600,
) -> FxContext:
    """Build context from history available at the current closed bar only."""
    if len(rows) < 60:
        raise ValueError("at least 60 bars are required for FX context")
    window = list(rows[-max(60, int(lookback)):])
    if int(bar_seconds) <= 0:
        raise ValueError("bar_seconds must be positive")
    bar_ts = int(float(window[-1][TS]))
    ts = bar_ts + int(bar_seconds)
    price = float(window[-1][CLOSE])
    a = atr(window, exclude_last=True)
    fs = entry_allowed(
        ts,
        events=events,
        price=price,
        avoid_low_liq_session=avoid_low_liquidity,
    )
    levels = unified_levels(
        window,
        lookback=min(len(window), lookback),
        include_round=False,
        atr_value=a if a == a and a > 0 else None,
    )
    return FxContext(
        symbol=instrument.symbol,
        ts=ts,
        bar_ts=bar_ts,
        bar_seconds=int(bar_seconds),
        price=price,
        atr=a,
        sessions=session_labels(ts),
        news_allowed=bool(fs.allow),
        news_reason=fs.reason,
        levels=levels,
        range_state=range_state(window),
        regime_state=regime_probs(window),
        elder_state=elder_bias(window, require_with_tide=False),
        round_levels=instrument_round_levels(instrument, price),
    )
