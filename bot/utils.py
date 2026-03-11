"""
bot/utils.py — Misc pure utility functions.
No external project dependencies. Safe to import anywhere.
Extracted from smart_pump_reversal_bot.py.
"""
from __future__ import annotations
import time


def now_s() -> int:
    """Current UTC time in seconds."""
    return int(time.time())


def _to_float_safe(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _today_ymd() -> str:
    """Return today as 'YYYY-MM-DD' (UTC)."""
    t = time.gmtime()
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"


def base_from_usdt(s: str) -> str:
    """'BTCUSDT' → 'BTC'. Strips trailing USDT."""
    return str(s).replace("USDT", "")


def dist_pct(price: float, level: float) -> float:
    """Signed percentage distance: (price - level) / level * 100.
    Positive = price above level, negative = below.
    Matches original implementation in smart_pump_reversal_bot.py.
    """
    return (price - level) / max(1e-12, level) * 100.0
