"""Helpers for live kline adapters."""
from __future__ import annotations

import time
from typing import Optional


def interval_to_ms(interval: str) -> int:
    iv = str(interval).strip().upper()
    if iv.isdigit():
        return max(1, int(iv)) * 60 * 1000
    mapping = {
        "D": 24 * 60 * 60 * 1000,
        "W": 7 * 24 * 60 * 60 * 1000,
        "M": 30 * 24 * 60 * 60 * 1000,
    }
    return int(mapping.get(iv, 5 * 60 * 1000))


def ts_to_ms(value) -> int:
    try:
        ts = int(float(value))
    except Exception:
        return 0
    return ts if ts > 10**11 else ts * 1000


def closed_kline_rows(rows: list, interval: str, *, now_ms: Optional[int] = None) -> list:
    """Return only closed candles from a Bybit-style kline response."""
    if not rows:
        return rows
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    interval_ms = interval_to_ms(interval)
    last = rows[-1]
    last_start_ms = ts_to_ms(last[0] if isinstance(last, (list, tuple)) and last else 0)
    if last_start_ms > 0 and now_ms < last_start_ms + interval_ms:
        return list(rows[:-1])
    return list(rows)


def fetch_closed_klines(fetch_klines, symbol: str, interval: str, limit: int) -> list:
    """Fetch one extra row and trim the still-open candle if present."""
    req_limit = max(1, int(limit)) + 1
    rows = fetch_klines(symbol, interval, req_limit)
    closed = closed_kline_rows(rows, interval)
    return closed[-int(limit):]
