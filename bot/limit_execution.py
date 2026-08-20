"""Paper-only passive-limit execution model for strategy entry experiments.

This module has no exchange client and no order method.  It compares the same
signal under two execution policies:

* baseline: cross the spread immediately;
* challenger: rest at best bid (buy) / best ask (sell) for 60 seconds, then
  cross the spread if the passive order was not filled.

A disappearing quote is not a fill.  The paper order fills only after public
trade prints consume the queue that was ahead of it plus its own quantity.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class TradePrint:
    ts_ms: int
    price: float
    qty: float
    aggressor_side: str


@dataclass(frozen=True)
class PaperLimitResult:
    authority: str
    side: str
    mode: str
    signal_ts_ms: int
    deadline_ts_ms: int
    baseline_market_price: float
    limit_price: float
    execution_price: float
    fee_bps: float
    maker_fee_bps: float
    taker_fee_bps: float
    queue_ahead_qty: float
    order_qty: float
    qualifying_trade_qty: float
    fill_ts_ms: int | None
    savings_bps_vs_market: float
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def _side(value: str) -> str:
    side = str(value or "").strip().lower()
    if side in {"buy", "long"}:
        return "buy"
    if side in {"sell", "short"}:
        return "sell"
    raise ValueError(f"unsupported side: {value}")


def _positive(value: float, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return parsed


def _net_value(side: str, price: float, fee_bps: float) -> float:
    fee = float(fee_bps) / 10_000.0
    return price * (1.0 + fee) if side == "buy" else price * (1.0 - fee)


def simulate_limit_then_market(
    *,
    side: str,
    signal_ts_ms: int,
    best_bid: float,
    best_ask: float,
    queue_ahead_qty: float,
    order_qty: float,
    trades: Iterable[TradePrint],
    fallback_bid: float,
    fallback_ask: float,
    wait_seconds: int = 60,
    maker_fee_bps: float = 2.0,
    taker_fee_bps: float = 5.5,
) -> PaperLimitResult:
    """Simulate one paper order without any private API or money authority."""
    normalized_side = _side(side)
    bid = _positive(best_bid, "best_bid")
    ask = _positive(best_ask, "best_ask")
    if ask < bid:
        raise ValueError("crossed book at signal")
    qty = _positive(order_qty, "order_qty")
    queue = max(0.0, float(queue_ahead_qty))
    if not math.isfinite(queue):
        raise ValueError("queue_ahead_qty must be finite")
    if int(wait_seconds) <= 0:
        raise ValueError("wait_seconds must be > 0")

    signal_ts = int(signal_ts_ms)
    deadline = signal_ts + int(wait_seconds) * 1000
    limit_price = bid if normalized_side == "buy" else ask
    baseline_price = ask if normalized_side == "buy" else bid
    needed = queue + qty
    consumed = 0.0
    fill_ts: int | None = None

    for trade in sorted(trades, key=lambda row: int(row.ts_ms)):
        ts_ms = int(trade.ts_ms)
        if ts_ms < signal_ts or ts_ms > deadline:
            continue
        price = float(trade.price)
        trade_qty = max(0.0, float(trade.qty))
        aggressor = str(trade.aggressor_side or "").strip().lower()
        qualifies = (
            normalized_side == "buy" and aggressor == "sell" and price <= limit_price
        ) or (
            normalized_side == "sell" and aggressor == "buy" and price >= limit_price
        )
        if not qualifies:
            continue
        consumed += trade_qty
        if consumed + 1e-12 >= needed:
            fill_ts = ts_ms
            break

    if fill_ts is not None:
        mode = "maker"
        execution_price = limit_price
        fee_bps = float(maker_fee_bps)
        reason = "public_trade_through_consumed_visible_queue_and_order"
    else:
        mode = "market_fallback"
        execution_price = _positive(
            fallback_ask if normalized_side == "buy" else fallback_bid,
            "fallback_price",
        )
        fee_bps = float(taker_fee_bps)
        reason = "not_filled_within_wait_window"

    baseline_net = _net_value(normalized_side, baseline_price, taker_fee_bps)
    challenger_net = _net_value(normalized_side, execution_price, fee_bps)
    mid = (bid + ask) / 2.0
    savings = (
        (baseline_net - challenger_net) / mid * 10_000.0
        if normalized_side == "buy"
        else (challenger_net - baseline_net) / mid * 10_000.0
    )
    return PaperLimitResult(
        authority="paper_only_no_orders",
        side=normalized_side,
        mode=mode,
        signal_ts_ms=signal_ts,
        deadline_ts_ms=deadline,
        baseline_market_price=baseline_price,
        limit_price=limit_price,
        execution_price=execution_price,
        fee_bps=fee_bps,
        maker_fee_bps=float(maker_fee_bps),
        taker_fee_bps=float(taker_fee_bps),
        queue_ahead_qty=queue,
        order_qty=qty,
        qualifying_trade_qty=consumed,
        fill_ts_ms=fill_ts,
        savings_bps_vs_market=savings,
        reason=reason,
    )
