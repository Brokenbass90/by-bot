#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .metrics import Trade
from strategies.signals import TradeSignal


@dataclass
class Candle:
    ts: int  # ms
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


def aggregate_candles(base: List[Candle], group_n: int) -> List[Candle]:
    """Aggregate candles by fixed count (e.g., 12x5m => 1h). Assumes contiguous data."""
    if group_n <= 1:
        return base[:]
    out: List[Candle] = []
    for i in range(0, len(base), group_n):
        chunk = base[i:i + group_n]
        if len(chunk) < group_n:
            break
        o = chunk[0].o
        h = max(c.h for c in chunk)
        l = min(c.l for c in chunk)
        c = chunk[-1].c
        v = sum(ca.v for ca in chunk)
        out.append(Candle(ts=chunk[0].ts, o=o, h=h, l=l, c=c, v=v))
    return out


class KlineStore:
    """Provides local kline slices in the same shape strategies expect."""

    def __init__(self, symbol: str, candles_5m: List[Candle]):
        self.symbol = symbol
        self.c5 = candles_5m
        self.c15 = aggregate_candles(candles_5m, 3)
        self.c1h = aggregate_candles(candles_5m, 12)
        self.c4h = aggregate_candles(candles_5m, 48)
        self.i5 = -1

    def set_index(self, i5: int) -> None:
        self.i5 = i5

    def _slice(self, interval: str, limit: int) -> List[Candle]:
        if interval == "5":
            arr = self.c5
            i = self.i5
        elif interval == "15":
            arr = self.c15
            i = self.i5 // 3
            step = 3
        elif interval == "60":
            arr = self.c1h
            i = self.i5 // 12
        elif interval == "240":
            arr = self.c4h
            i = self.i5 // 48
        else:
            raise ValueError(f"Unsupported interval {interval}; expected 5/15/60/240")

        if i < 0:
            return []
        end = min(len(arr), i + 1)
        start = max(0, end - max(0, int(limit)))
        return arr[start:end]

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        """Return Bybit-like raw klines list-of-lists, oldest-first."""
        if symbol != self.symbol:
            raise ValueError("KlineStore is per-symbol")
        rows = []
        for c in self._slice(interval, limit):
            rows.append([str(c.ts), str(c.o), str(c.h), str(c.l), str(c.c), str(c.v), "0"])
        return rows

    def candles_1h_ohlc(self) -> List[Tuple[float, float, float, float]]:
        return [(c.o, c.h, c.l, c.c) for c in self._slice("60", 10**9)]

    def last_5m_ohlc(self) -> Tuple[float, float, float, float]:
        if self.i5 < 0:
            return (math.nan, math.nan, math.nan, math.nan)
        c = self.c5[self.i5]
        return (c.o, c.h, c.l, c.c)


@dataclass
class BacktestParams:
    starting_equity: float = 1000.0
    risk_pct: float = 0.01
    # Fixed per-trade notional cap (USD). If None, a dynamic cap is derived as:
    #   cap = equity * leverage / max_positions
    # This lets you simulate (roughly) a portfolio that can hold several
    # concurrent positions by limiting each trade to a fraction of equity.
    cap_notional_usd: Optional[float] = 1000.0
    leverage: float = 1.0
    max_positions: int = 1
    fee_bps: float = 6.0
    slippage_bps: float = 2.0


@dataclass
class Position:
    side: str
    entry_price: float
    sl: float  # dynamic stop (may trail)
    qty: float  # initial qty
    remaining_qty: float
    entry_ts: int
    entry_i: int

    initial_sl: float = 0.0
    equity_at_entry: float = 0.0

    # Multi-target plan (optional)
    tps: List[float] = field(default_factory=list)
    tp_qty_remaining: List[float] = field(default_factory=list)

    # Trailing stop config (ATR-based)
    trailing_atr_mult: float = 0.0
    trailing_atr_period: int = 14
    hh_since_entry: float = float("-inf")
    ll_since_entry: float = float("inf")

    # Time stop (bars of 5m)
    time_stop_bars: int = 0

    # Accounting
    entry_fee: float = 0.0
    exit_fees: float = 0.0
    realized_pnl: float = 0.0
    exit_notional_sum: float = 0.0
    exit_ts_last: int = 0
    reasons: List[str] = field(default_factory=list)


def _apply_slippage(price: float, side: str, is_entry: bool, slippage_bps: float) -> float:
    bps = slippage_bps / 10000.0
    if side == "long":
        return price * (1 + bps) if is_entry else price * (1 - bps)
    else:
        return price * (1 - bps) if is_entry else price * (1 + bps)


def _fees(notional: float, fee_bps: float) -> float:
    return abs(notional) * (fee_bps / 10000.0)


def _calc_qty(equity: float, sig: TradeSignal, risk_pct: float, cap_notional_usd: Optional[float]) -> float:
    # risk sizing by stop distance
    risk_usd = max(0.0, equity * risk_pct)
    if risk_usd <= 0:
        return 0.0

    if sig.side == "long":
        stop_dist = sig.entry - sig.sl
    else:
        stop_dist = sig.sl - sig.entry
    if stop_dist <= 0:
        return 0.0

    qty = risk_usd / stop_dist

    qty_raw = qty
    if cap_notional_usd is not None and cap_notional_usd > 0:
        max_qty = cap_notional_usd / max(1e-12, sig.entry)
        qty = min(qty, max_qty)

    # Skip micro-risk trades where desired size is heavily capped by notional limits
    # (fees/slippage dominate, expectancy degrades).
    min_fill = float(os.getenv("MIN_NOTIONAL_FILL_FRAC", "0.40"))
    if qty_raw > 0:
        fill = qty / qty_raw
        if fill < min_fill:
            return 0.0

    return max(0.0, qty)


def _compute_atr_series(candles: List[Candle], period: int) -> List[float]:
    """Compute an ATR series (Wilder's smoothing) over 5m candles.

    Returns a list aligned with `candles` indices. Values before enough history are NaN.
    """
    n = len(candles)
    out = [float("nan")] * n
    if period <= 0 or n < period + 2:
        return out

    trs: List[float] = []
    for i in range(1, n):
        h = candles[i].h
        l = candles[i].l
        prev_c = candles[i - 1].c
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)

    # First ATR as simple average of first `period` TRs.
    if len(trs) < period:
        return out
    atr = sum(trs[:period]) / float(period)
    out[period] = atr
    alpha = 1.0 / float(period)
    for i in range(period + 1, n):
        tr = trs[i - 1]
        atr = (1 - alpha) * atr + alpha * tr
        out[i] = atr
    return out


def _tp_hits_in_bar(pos: Position, bar: Candle) -> List[int]:
    """Return indices of TP levels hit in this bar (based on OHLC extremes)."""
    hits: List[int] = []
    if not pos.tps:
        return hits
    if pos.side == "long":
        for k, tp in enumerate(pos.tps):
            if k < len(pos.tp_qty_remaining) and pos.tp_qty_remaining[k] > 0 and bar.h >= tp:
                hits.append(k)
    else:
        for k, tp in enumerate(pos.tps):
            if k < len(pos.tp_qty_remaining) and pos.tp_qty_remaining[k] > 0 and bar.l <= tp:
                hits.append(k)
    return hits


def _stop_hit(pos: Position, bar: Candle) -> bool:
    if pos.side == "long":
        return bar.l <= pos.sl
    return bar.h >= pos.sl


def _outcome_from_reason(reason: str) -> str:
    r = (reason or "").upper()
    if "SL" in r:
        return "sl"
    if "TP" in r:
        return "tp"
    if "TIME" in r:
        return "time"
    if "EOP" in r or "END" in r:
        return "time"
    return "manual"


SignalFn = Callable[[KlineStore, Candle], Optional[TradeSignal]]


def run_symbol_backtest(
    store: KlineStore,
    *,
    strategy_name: str,
    signal_fn: SignalFn,
    params: BacktestParams,
) -> Tuple[List[Trade], List[float]]:
    """Run a 5m backtest for a single symbol.

    Note: `backtest.run_month` constructs a :class:`KlineStore` per symbol and
    passes it in. We accept the store as the first positional argument to keep
    the CLI stable across project repacks.
    """

    symbol = store.symbol
    candles_5m = store.c5
    equity = float(params.starting_equity)
    curve: List[float] = [equity]
    trades: List[Trade] = []

    atr_cache: Dict[int, List[float]] = {}

    def _atr_series(period: int) -> List[float]:
        p = int(max(2, period))
        s = atr_cache.get(p)
        if s is None:
            s = _compute_atr_series(candles_5m, p)
            atr_cache[p] = s
        return s

    def _close_position(pos: Position, exit_ts: int, reason: str) -> None:
        nonlocal equity
        if pos.qty <= 0:
            return
        # Net PnL includes entry fee (already paid from equity at entry).
        net_pnl = float(pos.realized_pnl) - float(pos.entry_fee)
        fees = float(pos.entry_fee) + float(pos.exit_fees)
        exit_price = (pos.exit_notional_sum / pos.qty) if pos.exit_notional_sum > 0 else pos.entry_price
        pnl_pct = 0.0 if pos.equity_at_entry == 0 else (net_pnl / pos.equity_at_entry)
        final_reason = "+".join([r for r in (pos.reasons + [reason]) if r])
        trades.append(
            Trade(
                strategy=strategy_name,
                symbol=symbol,
                side=pos.side,
                entry_ts=pos.entry_ts,
                exit_ts=exit_ts,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                qty=pos.qty,
                pnl=net_pnl,
                pnl_pct_equity=pnl_pct,
                fees=fees,
                outcome=_outcome_from_reason(final_reason),
                reason=final_reason,
            )
        )

    pos: Optional[Position] = None

    for i, bar in enumerate(candles_5m):
        store.set_index(i)

        # -------------------- Manage open position --------------------
        if pos is not None and i > pos.entry_i:
            # Update extrema since entry for trailing calculations.
            pos.hh_since_entry = max(pos.hh_since_entry, float(bar.h))
            pos.ll_since_entry = min(pos.ll_since_entry, float(bar.l))

            stop_hit = _stop_hit(pos, bar)
            tp_hits = _tp_hits_in_bar(pos, bar)

            # Conservative: if both TP and SL could happen in the same bar, assume SL first.
            if stop_hit and tp_hits:
                exit_qty = pos.remaining_qty
                if exit_qty > 0:
                    raw_exit = float(pos.sl)
                    exit_px = _apply_slippage(raw_exit, pos.side, is_entry=False, slippage_bps=params.slippage_bps)
                    exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
                    pnl_portion = (exit_px - pos.entry_price) * exit_qty if pos.side == "long" else (pos.entry_price - exit_px) * exit_qty
                    equity += (pnl_portion - exit_fee)
                    pos.realized_pnl += (pnl_portion - exit_fee)
                    pos.exit_fees += exit_fee
                    pos.exit_notional_sum += exit_px * exit_qty
                    pos.exit_ts_last = int(bar.ts)
                    pos.remaining_qty = 0.0
                pos.reasons.append("TRAIL_SL" if (pos.trailing_atr_mult > 0 and pos.sl != pos.initial_sl) else "SL")
                _close_position(pos, int(bar.ts), "SL_TP_SAME_BAR")
                pos = None

            else:
                # --- Take profits (may be partial) ---
                if tp_hits and pos.remaining_qty > 0:
                    for k in sorted(tp_hits):
                        if pos.remaining_qty <= 0:
                            break
                        if k >= len(pos.tp_qty_remaining):
                            continue
                        qty_to_exit = min(pos.remaining_qty, pos.tp_qty_remaining[k])
                        if qty_to_exit <= 0:
                            continue
                        raw_exit = float(pos.tps[k])
                        exit_px = _apply_slippage(raw_exit, pos.side, is_entry=False, slippage_bps=params.slippage_bps)
                        exit_fee = _fees(exit_px * qty_to_exit, params.fee_bps)
                        pnl_portion = (exit_px - pos.entry_price) * qty_to_exit if pos.side == "long" else (pos.entry_price - exit_px) * qty_to_exit
                        equity += (pnl_portion - exit_fee)
                        pos.realized_pnl += (pnl_portion - exit_fee)
                        pos.exit_fees += exit_fee
                        pos.exit_notional_sum += exit_px * qty_to_exit
                        pos.exit_ts_last = int(bar.ts)
                        pos.tp_qty_remaining[k] -= qty_to_exit
                        pos.remaining_qty -= qty_to_exit
                        pos.reasons.append(f"TP{k+1}")

                # --- Stop loss (including trailing) ---
                if pos is not None and pos.remaining_qty > 0 and stop_hit:
                    exit_qty = pos.remaining_qty
                    raw_exit = float(pos.sl)
                    exit_px = _apply_slippage(raw_exit, pos.side, is_entry=False, slippage_bps=params.slippage_bps)
                    exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
                    pnl_portion = (exit_px - pos.entry_price) * exit_qty if pos.side == "long" else (pos.entry_price - exit_px) * exit_qty
                    equity += (pnl_portion - exit_fee)
                    pos.realized_pnl += (pnl_portion - exit_fee)
                    pos.exit_fees += exit_fee
                    pos.exit_notional_sum += exit_px * exit_qty
                    pos.exit_ts_last = int(bar.ts)
                    pos.remaining_qty = 0.0

                    pos.reasons.append("TRAIL_SL" if (pos.trailing_atr_mult > 0 and pos.sl != pos.initial_sl) else "SL")
                    _close_position(pos, int(bar.ts), "SL")
                    pos = None

                # --- Time stop at close ---
                if pos is not None and pos.remaining_qty > 0 and pos.time_stop_bars > 0:
                    if (i - pos.entry_i) >= int(pos.time_stop_bars):
                        exit_qty = pos.remaining_qty
                        raw_exit = float(bar.c)
                        exit_px = _apply_slippage(raw_exit, pos.side, is_entry=False, slippage_bps=params.slippage_bps)
                        exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
                        pnl_portion = (exit_px - pos.entry_price) * exit_qty if pos.side == "long" else (pos.entry_price - exit_px) * exit_qty
                        equity += (pnl_portion - exit_fee)
                        pos.realized_pnl += (pnl_portion - exit_fee)
                        pos.exit_fees += exit_fee
                        pos.exit_notional_sum += exit_px * exit_qty
                        pos.exit_ts_last = int(bar.ts)
                        pos.remaining_qty = 0.0
                        pos.reasons.append("TIME")
                        _close_position(pos, int(bar.ts), "TIME")
                        pos = None

                # --- Update trailing stop for next bar ---
                if pos is not None and pos.remaining_qty > 0 and pos.trailing_atr_mult > 0:
                    ser = _atr_series(pos.trailing_atr_period)
                    a = float(ser[i]) if i < len(ser) else float("nan")
                    if a > 0 and a == a:  # not NaN
                        if pos.side == "long":
                            new_sl = pos.hh_since_entry - float(pos.trailing_atr_mult) * a
                            if new_sl > pos.sl:
                                pos.sl = new_sl
                        else:
                            new_sl = pos.ll_since_entry + float(pos.trailing_atr_mult) * a
                            if new_sl < pos.sl:
                                pos.sl = new_sl

        # -------------------- Entry at close --------------------
        if pos is None:
            sig = signal_fn(store, bar)
            if sig is not None and sig.validate():
                cap = params.cap_notional_usd
                if cap is None:
                    mp = max(1, int(params.max_positions))
                    cap = float(equity) * float(params.leverage) / mp
                sig_qty = _calc_qty(equity, sig, params.risk_pct, cap)
                if sig_qty > 0:
                    entry_px = _apply_slippage(sig.entry, sig.side, is_entry=True, slippage_bps=params.slippage_bps)

                    # Build TP plan
                    if sig.tps:
                        tps = [float(x) for x in sig.tps]
                        fr = [float(x) for x in (sig.tp_fracs or [])]
                        if not fr:
                            fr = [1.0 / len(tps)] * len(tps)
                        s = sum(fr)
                        if s > 1.000001:
                            fr = [x / s for x in fr]
                        tp_qty_remaining = [max(0.0, sig_qty * x) for x in fr]
                        # legacy tp is the last target (for compatibility)
                        legacy_tp = float(tps[-1])
                    else:
                        tps = [float(sig.tp)]
                        tp_qty_remaining = [float(sig_qty)]
                        legacy_tp = float(sig.tp)

                    entry_fee = _fees(entry_px * sig_qty, params.fee_bps)
                    equity_before_entry = equity
                    equity -= entry_fee

                    pos = Position(
                        side=sig.side,
                        entry_price=entry_px,
                        sl=float(sig.sl),
                        qty=float(sig_qty),
                        remaining_qty=float(sig_qty),
                        entry_ts=int(bar.ts),
                        entry_i=int(i),
                        initial_sl=float(sig.sl),
                        equity_at_entry=float(equity_before_entry),
                        tps=tps,
                        tp_qty_remaining=tp_qty_remaining,
                        trailing_atr_mult=float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0),
                        trailing_atr_period=int(getattr(sig, "trailing_atr_period", 14) or 14),
                        hh_since_entry=float(entry_px),
                        ll_since_entry=float(entry_px),
                        time_stop_bars=int(getattr(sig, "time_stop_bars", 0) or 0),
                        entry_fee=float(entry_fee),
                    )

        curve.append(equity)

    # End-of-period: force close if any position remains.
    if pos is not None and pos.remaining_qty > 0 and candles_5m:
        last = candles_5m[-1]
        exit_qty = pos.remaining_qty
        raw_exit = float(last.c)
        exit_px = _apply_slippage(raw_exit, pos.side, is_entry=False, slippage_bps=params.slippage_bps)
        exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
        pnl_portion = (exit_px - pos.entry_price) * exit_qty if pos.side == "long" else (pos.entry_price - exit_px) * exit_qty
        equity += (pnl_portion - exit_fee)
        pos.realized_pnl += (pnl_portion - exit_fee)
        pos.exit_fees += exit_fee
        pos.exit_notional_sum += exit_px * exit_qty
        pos.exit_ts_last = int(last.ts)
        pos.remaining_qty = 0.0
        pos.reasons.append("EOP")
        _close_position(pos, int(last.ts), "EOP")

    return trades, curve
