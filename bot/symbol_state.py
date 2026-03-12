"""
bot/symbol_state.py — Per-symbol in-memory state (SymState) and registry.

Extracted from smart_pump_reversal_bot.py (lines ~2332-2425).
Depends only on: standard library + indicators.py (project-level, no circular deps).
"""
from __future__ import annotations

import collections
from typing import Dict, Optional, Tuple

# ─── Constants (matched to main bot values; update here if changed there) ───
_WINDOW_SEC: int = 300   # WINDOW_SEC in main file
_BASE_WINDOWS: int = 12  # BASE_WINDOWS in main file
_CTX_5M_SEC: int = 300   # CTX_5M_SEC in main file

# Indicator wrappers (indicators.py is in project root, importable from here
# as long as the project root is in sys.path — which it is when running the bot)
try:
    from indicators import (
        atr_pct_from_ohlc,
        rsi as _rsi_calc,
        ema_incremental,
        candle_pattern as _candle_pattern_detect,
        engulfing as _engulfing_bear,
        trade_quality as _calc_trade_quality,
    )
    _INDICATORS_OK = True
except ImportError as _ind_exc:
    import sys as _sys
    print(
        f"[bot/symbol_state] WARNING: indicators.py import failed: {_ind_exc}. "
        "All indicator functions will return FALLBACK constants "
        "(atr_pct=0.8, rsi=50.0, ema=price, quality=0.0). "
        "Signals and sizing may be incorrect. Check that indicators.py is in sys.path.",
        file=_sys.stderr,
    )
    _INDICATORS_OK = False


# ─── SymState ───────────────────────────────────────────────────────────────

class SymState:
    """Per-symbol rolling state: trades, prices, 5m bars, EMAs, etc."""

    __slots__ = (
        "trades", "prices", "win_hist", "last_eval_ts", "last_alert",
        "highs", "lows", "closes", "last_pump", "q_hist",
        "ema_fast", "ema_slow", "ctx5m", "last_bounce_try",
        "bars5m", "cur5_id", "cur5_o", "cur5_h", "cur5_l", "cur5_c", "cur5_quote",
    )

    def __init__(self):
        self.trades = collections.deque()
        self.prices = collections.deque()
        self.win_hist = collections.deque(maxlen=_BASE_WINDOWS)
        self.last_eval_ts: int = 0
        self.last_alert: int = 0
        self.highs  = collections.deque(maxlen=240)
        self.lows   = collections.deque(maxlen=240)
        self.closes = collections.deque(maxlen=240)
        self.last_pump = None
        self.q_hist = collections.deque(maxlen=2)
        self.ema_fast = None
        self.ema_slow = None
        self.ctx5m = collections.deque()
        self.last_bounce_try: int = 0

        self.cur5_id = None
        self.bars5m = collections.deque(maxlen=300)
        self.cur5_o = self.cur5_h = self.cur5_l = self.cur5_c = None
        self.cur5_quote: float = 0.0


# Global registry: (exchange, symbol) → SymState
# Imported by the main bot file — same dict object is shared.
STATE: Dict[Tuple[str, str], SymState] = {}


def S(exch: str, sym: str) -> SymState:
    """Get or create SymState for (exchange, symbol)."""
    k = (exch, sym)
    st = STATE.get(k)
    if st is None:
        st = SymState()
        STATE[k] = st
    return st


def update_5m_bar(st: SymState, t: int, p: float, qq: float) -> None:
    """Update the current 5-minute bar in SymState."""
    bar_id = t // 300
    if st.cur5_id != bar_id:
        # Close previous bar
        if st.cur5_id is not None and st.cur5_o is not None:
            st.bars5m.append({
                "id": st.cur5_id,
                "o": st.cur5_o, "h": st.cur5_h, "l": st.cur5_l, "c": st.cur5_c,
                "quote": st.cur5_quote,
            })
        # Start new bar
        st.cur5_id = bar_id
        st.cur5_o = st.cur5_h = st.cur5_l = st.cur5_c = p
        st.cur5_quote = 0.0
    else:
        st.cur5_h = max(st.cur5_h, p)
        st.cur5_l = min(st.cur5_l, p)
        st.cur5_c = p
    st.cur5_quote += qq


def trim(st: SymState, ts: int) -> None:
    """Remove stale entries from SymState rolling windows."""
    cut = ts - _WINDOW_SEC * 2
    while st.trades and st.trades[0][0] < cut:
        st.trades.popleft()
    while st.prices and st.prices[0][0] < cut:
        st.prices.popleft()
    cut5 = ts - (_CTX_5M_SEC + 10)
    while st.ctx5m and st.ctx5m[0][0] < cut5:
        st.ctx5m.popleft()


# ─── Indicator wrappers (thin delegates to indicators.py) ───────────────────

def calc_atr_pct(h, l, c, period: int = 14) -> float:
    if _INDICATORS_OK:
        return atr_pct_from_ohlc(list(h), list(l), list(c), period=period, fallback=0.8)
    return 0.8


def calc_rsi(closes, period: int = 14) -> float:
    if _INDICATORS_OK:
        return _rsi_calc(list(closes), period=period)
    return 50.0


def ema_val(prev: Optional[float], price: float, length: int) -> float:
    if _INDICATORS_OK:
        return ema_incremental(prev, float(price), length)
    return float(price)


def candle_pattern(open_p, close_p, high_p, low_p) -> Optional[str]:
    if _INDICATORS_OK:
        return _candle_pattern_detect(float(open_p), float(close_p), float(high_p), float(low_p))
    return None


def engulfing(prev_o, prev_c, o, c) -> bool:
    if _INDICATORS_OK:
        return _engulfing_bear(prev_o, prev_c, float(o), float(c))
    return False


def trade_quality(trades: list, q_total: float) -> float:
    if _INDICATORS_OK:
        return _calc_trade_quality(trades, float(q_total))
    return 0.0
