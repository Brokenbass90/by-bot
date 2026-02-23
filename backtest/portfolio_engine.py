#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Portfolio backtest engine (multi-symbol, multi-strategy).

This is a *simple* portfolio simulator designed for our workflow:
1) Tune each strategy in isolation with ``run_month.py`` (per-symbol).
2) When strategies look reasonable, run a combined portfolio backtest where
   strategies compete for the same capital and position slots.

Assumptions / current limitations (intentional for speed and safety):
- One open position per symbol.
- Entry/exit are simulated on 5m candles with conservative intrabar rules.
- When multiple strategies signal on the same bar for a symbol, we take the
  first one per the provided strategy order.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import inspect
import os
from typing import Callable, Dict, List, Optional, Tuple

from backtest.engine import (
    BacktestParams,
    Candle,
    KlineStore,
    Position,
    _apply_slippage,
    _calc_qty,
    _compute_atr_series,
    _fees,
    _outcome_from_reason,
    _stop_hit,
    _tp_hits_in_bar,
)


# ---------------------------------------------------------------------------
# Async compatibility
# Some strategy wrappers expose async maybe_signal() plus a sync adapter.
# Be defensive: if selector returns an awaitable, run it to completion here.
_PORTFOLIO_LOOP: Optional[asyncio.AbstractEventLoop] = None

def _run_awaitable(x):
    global _PORTFOLIO_LOOP
    if _PORTFOLIO_LOOP is None or _PORTFOLIO_LOOP.is_closed():
        _PORTFOLIO_LOOP = asyncio.new_event_loop()
    try:
        return _PORTFOLIO_LOOP.run_until_complete(x)
    except RuntimeError:
        # If we're already inside a running loop (rare in CLI), fall back to a fresh loop.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(x)
        finally:
            loop.close()
from backtest.metrics import Trade


@dataclass
class PortfolioResult:
    trades: List[Trade]
    equity_curve: List[float]


# Signature: given (symbol, store, ts_ms, last_price) -> TradeSignal|None
SignalSelector = Callable[[str, KlineStore, int, float], Optional[object]]


def _csv_set(name: str) -> set[str]:
    raw = os.getenv(name, "") or ""
    return {p.strip().lower() for p in str(raw).split(",") if p.strip()}


def run_portfolio_backtest(
    stores: Dict[str, KlineStore],
    selector: SignalSelector,
    *,
    params: BacktestParams,
    symbols_order: Optional[List[str]] = None,
) -> PortfolioResult:
    """Run a combined portfolio backtest across multiple symbols.

    `stores` must all contain 5m candles aligned in time (as produced by
    `run_month.py` loader). We iterate by index up to the minimum length.
    """

    if not stores:
        return PortfolioResult(trades=[], equity_curve=[float(params.starting_equity)])

    syms = symbols_order or list(stores.keys())
    min_len = min(len(stores[s].c5) for s in syms)

    equity = float(params.starting_equity)
    curve: List[float] = [equity]
    trades: List[Trade] = []

    # One open position per symbol, plus which strategy opened it.
    pos_by_sym: Dict[str, Position] = {}
    pos_strat: Dict[str, str] = {}
    cooldown_until_i: Dict[str, int] = {}

    sl_cooldown_bars = max(0, int(os.getenv("PORTFOLIO_SL_COOLDOWN_BARS", "0") or 0))
    sl_cooldown_strategies = _csv_set("PORTFOLIO_SL_COOLDOWN_STRATEGIES") or {"inplay_breakout"}

    # ATR cache per symbol, keyed by period.
    atr_cache: Dict[str, Dict[int, List[float]]] = {s: {} for s in syms}

    def _atr(sym: str, period: int) -> List[float]:
        cache = atr_cache[sym]
        if period not in cache:
            cache[period] = _compute_atr_series(stores[sym].c5, period)
        return cache[period]

    def _close(sym: str, p: Position, exit_ts: int, reason: str):
        nonlocal equity

        if p.remaining_qty > 1e-12:
            # Should not happen; portfolio engine expects positions closed fully.
            pass

        avg_exit = (p.exit_notional_sum / p.qty) if p.qty > 0 else p.entry_price
        net_pnl = p.realized_pnl - p.entry_fee
        fees_total = p.entry_fee + p.exit_fees

        trades.append(
            Trade(
                strategy=pos_strat.get(sym, "unknown"),
                symbol=sym,
                side=p.side,
                entry_ts=p.entry_ts,
                exit_ts=exit_ts,
                entry_price=p.entry_price,
                exit_price=avg_exit,
                qty=p.qty,
                pnl=net_pnl,
                pnl_pct_equity=(net_pnl / p.equity_at_entry) if p.equity_at_entry else 0.0,
                fees=fees_total,
                outcome=_outcome_from_reason(reason),
                reason=reason,
            )
        )

        strat_name = str(pos_strat.get(sym, "unknown") or "").lower()
        if (
            sl_cooldown_bars > 0
            and ("SL" in str(reason or "").upper())
            and (strat_name in sl_cooldown_strategies)
        ):
            cooldown_until_i[sym] = i + sl_cooldown_bars

        pos_by_sym.pop(sym, None)
        pos_strat.pop(sym, None)

    for i in range(min_len):
        # Advance all stores to the same index.
        for s in syms:
            stores[s].set_index(i)

        # 1) Manage exits for all open positions first.
        for sym in list(pos_by_sym.keys()):
            p = pos_by_sym[sym]
            bar = stores[sym].c5[i]

            # Update extremes
            p.hh_since_entry = max(p.hh_since_entry, bar.h)
            p.ll_since_entry = min(p.ll_since_entry, bar.l)

            stop_hit = _stop_hit(p, bar)
            tp_hits = _tp_hits_in_bar(p, bar)

            # Conservative: if SL and any TP in same candle, assume SL first.
            if stop_hit and tp_hits:
                raw = p.sl
                exit_px = _apply_slippage(raw, p.side, is_entry=False, slippage_bps=params.slippage_bps)
                exit_qty = p.remaining_qty
                exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
                pnl_portion = (exit_px - p.entry_price) * exit_qty if p.side == "long" else (p.entry_price - exit_px) * exit_qty
                equity += pnl_portion - exit_fee
                p.realized_pnl += pnl_portion - exit_fee
                p.exit_fees += exit_fee
                p.exit_notional_sum += exit_px * exit_qty
                p.remaining_qty = 0.0
                reason = "+".join(p.reasons + ["SL_same_bar"])
                _close(sym, p, bar.ts, reason)
                continue

            # Take partial TPs (in index order)
            if tp_hits:
                for idx in sorted(tp_hits):
                    if p.remaining_qty <= 1e-12:
                        break
                    want = p.tp_qty_remaining[idx]
                    if want <= 1e-12:
                        continue
                    qty = min(p.remaining_qty, want)
                    raw = p.tps[idx]
                    exit_px = _apply_slippage(raw, p.side, is_entry=False, slippage_bps=params.slippage_bps)
                    exit_fee = _fees(exit_px * qty, params.fee_bps)
                    pnl_portion = (exit_px - p.entry_price) * qty if p.side == "long" else (p.entry_price - exit_px) * qty
                    equity += pnl_portion - exit_fee
                    p.realized_pnl += pnl_portion - exit_fee
                    p.exit_fees += exit_fee
                    p.exit_notional_sum += exit_px * qty
                    p.remaining_qty -= qty
                    p.tp_qty_remaining[idx] = max(0.0, want - qty)
                    p.reasons.append(f"TP{idx+1}")

                if p.remaining_qty <= 1e-12:
                    p.remaining_qty = 0.0
                    reason = "+".join(p.reasons) if p.reasons else "TP"
                    _close(sym, p, bar.ts, reason)
                    continue

            # Stop loss (if still open)
            if stop_hit:
                raw = p.sl
                exit_px = _apply_slippage(raw, p.side, is_entry=False, slippage_bps=params.slippage_bps)
                exit_qty = p.remaining_qty
                exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
                pnl_portion = (exit_px - p.entry_price) * exit_qty if p.side == "long" else (p.entry_price - exit_px) * exit_qty
                equity += pnl_portion - exit_fee
                p.realized_pnl += pnl_portion - exit_fee
                p.exit_fees += exit_fee
                p.exit_notional_sum += exit_px * exit_qty
                p.remaining_qty = 0.0
                tag = "TRAIL_SL" if (p.trailing_atr_mult > 0.0 and abs(p.sl - p.initial_sl) > 1e-9) else "SL"
                reason = "+".join(p.reasons + [tag])
                _close(sym, p, bar.ts, reason)
                continue

            # Time stop
            if p.time_stop_bars > 0 and (i - p.entry_i) >= p.time_stop_bars:
                raw = bar.c
                exit_px = _apply_slippage(raw, p.side, is_entry=False, slippage_bps=params.slippage_bps)
                exit_qty = p.remaining_qty
                exit_fee = _fees(exit_px * exit_qty, params.fee_bps)
                pnl_portion = (exit_px - p.entry_price) * exit_qty if p.side == "long" else (p.entry_price - exit_px) * exit_qty
                equity += pnl_portion - exit_fee
                p.realized_pnl += pnl_portion - exit_fee
                p.exit_fees += exit_fee
                p.exit_notional_sum += exit_px * exit_qty
                p.remaining_qty = 0.0
                reason = "+".join(p.reasons + ["TIME"]) if p.reasons else "TIME"
                _close(sym, p, bar.ts, reason)
                continue

            # Update trailing stop after processing exits on this bar.
            if p.trailing_atr_mult > 0 and i > p.entry_i:
                atr = _atr(sym, p.trailing_atr_period)[i]
                if atr and atr > 0:
                    if p.side == "long":
                        new_sl = p.hh_since_entry - p.trailing_atr_mult * atr
                        if new_sl > p.sl:
                            p.sl = new_sl
                    else:
                        new_sl = p.ll_since_entry + p.trailing_atr_mult * atr
                        if new_sl < p.sl:
                            p.sl = new_sl

        # 2) Entries (respect global max_positions)
        if len(pos_by_sym) < int(params.max_positions):
            for sym in syms:
                if len(pos_by_sym) >= int(params.max_positions):
                    break
                if sym in pos_by_sym:
                    continue
                if int(cooldown_until_i.get(sym, -1)) > i:
                    continue

                store = stores[sym]
                bar = store.c5[i]
                sig = selector(sym, store, bar.ts, bar.c)
                if inspect.isawaitable(sig):
                    sig = _run_awaitable(sig)
                if sig is None:
                    continue

                # Duck-typed TradeSignal
                try:
                    sig.validate()
                except Exception:
                    continue

                cap = params.cap_notional_usd
                if cap is None:
                    cap = (equity * float(params.leverage)) / max(1, int(params.max_positions))

                qty = _calc_qty(equity, sig, params.risk_pct, cap)
                if qty <= 0:
                    continue

                entry_px = _apply_slippage(sig.entry, sig.side, is_entry=True, slippage_bps=params.slippage_bps)
                entry_fee = _fees(entry_px * qty, params.fee_bps)
                equity -= entry_fee

                legacy_tp = getattr(sig, "tp", 0.0)
                tps = list(getattr(sig, "tps", []) or [])
                if not tps:
                    if legacy_tp and legacy_tp > 0:
                        tps = [float(legacy_tp)]
                    else:
                        tps = []
                fracs = list(getattr(sig, "tp_fracs", []) or [])

                if not fracs:
                    if tps:
                        fracs = [1.0]
                        if len(tps) > 1:
                            fracs = [1.0 / len(tps)] * len(tps)
                if fracs and sum(fracs) > 1.0:
                    s = sum(fracs)
                    fracs = [x / s for x in fracs]

                tp_qty_remaining: List[float] = []
                if not tps:
                    tp_qty_remaining = []
                elif len(tps) == 1 and (not fracs or fracs[0] >= 0.999):
                    tp_qty_remaining = [qty]
                else:
                    for k in range(len(tps)):
                        f = fracs[k] if k < len(fracs) else 0.0
                        tp_qty_remaining.append(max(0.0, qty * float(f)))

                p = Position(
                    side=sig.side,
                    entry_price=entry_px,
                    sl=float(sig.sl),
                    qty=qty,
                    remaining_qty=qty,
                    entry_ts=bar.ts,
                    entry_i=i,
                    initial_sl=float(sig.sl),
                    equity_at_entry=equity + entry_fee,
                    tps=[float(x) for x in tps],
                    tp_qty_remaining=tp_qty_remaining,
                    trailing_atr_mult=float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0),
                    trailing_atr_period=int(getattr(sig, "trailing_atr_period", 14) or 14),
                    time_stop_bars=int(getattr(sig, "time_stop_bars", 0) or 0),
                    hh_since_entry=entry_px,
                    ll_since_entry=entry_px,
                    reasons=[(getattr(sig, "reason", "") or "").strip()] if (getattr(sig, "reason", "") or "").strip() else [],
                    entry_fee=entry_fee,
                )

                pos_by_sym[sym] = p
                pos_strat[sym] = str(getattr(sig, "strategy", "unknown"))

        curve.append(equity)

    # Force close all remaining positions at the last close.
    last_i = min_len - 1
    for sym in list(pos_by_sym.keys()):
        p = pos_by_sym[sym]
        bar = stores[sym].c5[last_i]
        raw = bar.c
        exit_px = _apply_slippage(raw, p.side, is_entry=False, slippage_bps=params.slippage_bps)
        qty = p.remaining_qty
        exit_fee = _fees(exit_px * qty, params.fee_bps)
        pnl_portion = (exit_px - p.entry_price) * qty if p.side == "long" else (p.entry_price - exit_px) * qty
        equity += pnl_portion - exit_fee
        p.realized_pnl += pnl_portion - exit_fee
        p.exit_fees += exit_fee
        p.exit_notional_sum += exit_px * qty
        p.remaining_qty = 0.0
        reason = "+".join(p.reasons + ["EOP"]) if p.reasons else "EOP"
        _close(sym, p, bar.ts, reason)

    if curve[-1] != equity:
        curve.append(equity)

    return PortfolioResult(trades=trades, equity_curve=curve)
