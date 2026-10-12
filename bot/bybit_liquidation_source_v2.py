"""Pure, opt-in V2 for public Bybit allLiquidation position-side semantics.

S=Buy means a LONG position was liquidated; S=Sell means SHORT. p is the
bankruptcy price, so qty*p is a notional proxy, not an execution-cost source.
No existing producer, historical file, consumer, client or runtime is changed.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

SCHEMA = "BYBIT_ALL_LIQUIDATION_SOURCE_V2"
OFFICIAL_SOURCE = "https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation"


def _positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def normalize_liquidation(raw: dict, *, topic_symbol: str = "", recv_ts_ms: int = 0) -> dict | None:
    """Bind raw S/T/s; unknown side/time is rejected rather than inferred."""
    if not isinstance(raw, dict):
        return None
    symbol, raw_side, timestamp = raw.get("s"), raw.get("S"), raw.get("T")
    if (not isinstance(symbol, str) or not symbol or symbol != symbol.strip()
            or raw_side not in ("Buy", "Sell") or type(timestamp) is not int or timestamp <= 0):
        return None
    if topic_symbol and symbol != topic_symbol:
        return None
    qty, price = _positive(raw.get("v")), _positive(raw.get("p"))
    if qty is None or price is None or not math.isfinite(qty * price):
        return None
    try:
        raw_bytes = json.dumps(raw, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError):
        return None
    side = "long" if raw_side == "Buy" else "short"
    return dict(schema=SCHEMA, source_topic="allLiquidation." + symbol,
                ts_ms=timestamp, symbol=symbol, side=side,
                liquidated_position_side=side, raw_position_side=raw_side,
                qty=qty, price=price, usd=round(qty * price, 8),
                price_basis="bankruptcy_price", usd_basis="bankruptcy_notional_proxy",
                recv_ts_ms=(recv_ts_ms if type(recv_ts_ms) is int and recv_ts_ms > 0 else None),
                raw_item_canonical_sha256=hashlib.sha256(raw_bytes).hexdigest())


def normalize_ws_message(message: dict, *, recv_ts_ms: int = 0) -> list[dict]:
    """Accept only allLiquidation batches; frame ts never replaces event T."""
    if not isinstance(message, dict):
        return []
    topic = message.get("topic")
    if not isinstance(topic, str) or not topic.startswith("allLiquidation."):
        return []
    symbol = topic[len("allLiquidation."):]
    if not symbol or "." in symbol:
        return []
    data = message.get("data")
    if not isinstance(data, list):
        return []
    events = []
    for raw in data:
        event = normalize_liquidation(raw, topic_symbol=symbol, recv_ts_ms=recv_ts_ms)
        if event is not None:
            events.append(event)
    return events
