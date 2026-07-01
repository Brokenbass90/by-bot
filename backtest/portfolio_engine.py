#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Portfolio backtest engine (multi-symbol, multi-strategy).

This is a *simple* portfolio simulator designed for our workflow:
1) Tune each strategy in isolation with ``run_month.py`` (per-symbol).
2) When strategies look reasonable, run a combined portfolio backtest where
   strategies compete for the same capital and position slots.

Assumptions / current limitations (intentional for speed and safety):
- One open position per symbol.
- Entry/exit are simulated on the store execution timeframe with conservative intrabar rules.
- When multiple strategies signal on the same bar for a symbol, we take the
  first one per the provided strategy order.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import copy
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

try:
    from bot.volume_exit import volume_fade_exit as _volume_fade_exit
except Exception:  # pragma: no cover - defensive
    _volume_fade_exit = None


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

    `stores` must all contain execution candles aligned in time. We iterate by
    index up to the minimum length of the execution series.
    """

    if not stores:
        return PortfolioResult(trades=[], equity_curve=[float(params.starting_equity)])

    syms = symbols_order or list(stores.keys())
    min_len = min(len(stores[s].exec_candles) for s in syms)

    equity = float(params.starting_equity)
    curve: List[float] = [equity]
    trades: List[Trade] = []

    # One open position per symbol, plus which strategy opened it.
    pos_by_sym: Dict[str, Position] = {}
    pos_strat: Dict[str, str] = {}
    cooldown_until_i: Dict[str, int] = {}
    pending_signals: Dict[str, Tuple[int, object]] = {}

    sl_cooldown_bars = max(0, int(os.getenv("PORTFOLIO_SL_COOLDOWN_BARS", "0") or 0))
    sl_cooldown_strategies = _csv_set("PORTFOLIO_SL_COOLDOWN_STRATEGIES") or {"inplay_breakout"}

    # Volume-fade early exit (owner setup A): close the runner when the impulse's
    # volume dies before reaching target. Additive, default OFF. See bot/volume_exit.py.
    _vol_exit_enable = (
        str(os.getenv("VOLUME_EXIT_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
        and _volume_fade_exit is not None
    )
    _vol_exit_strats = _csv_set("VOLUME_EXIT_STRATEGIES")  # empty = all strategies
    _vol_exit_baseline = max(2, int(os.getenv("VOLUME_EXIT_BASELINE_WINDOW", "20") or 20))
    _vol_exit_impulse = max(1, int(os.getenv("VOLUME_EXIT_IMPULSE_WINDOW", "3") or 3))
    _vol_exit_fade = float(os.getenv("VOLUME_EXIT_FADE_RATIO", "0.70") or 0.70)
    _vol_exit_peakfade = float(os.getenv("VOLUME_EXIT_PEAK_FADE_RATIO", "0.45") or 0.45)
    _vol_exit_stall = str(os.getenv("VOLUME_EXIT_REQUIRE_STALL", "1")).strip().lower() in {"1", "true", "yes", "on"}
    _vol_exit_bars = max(_vol_exit_baseline + 2 * _vol_exit_impulse + 2, 30)

    # Global strategy-level cooldown: after any SL in strategy X, ALL symbols
    # of that strategy are blocked for PORTFOLIO_GLOBAL_SL_COOLDOWN_BARS bars.
    # Env: PORTFOLIO_GLOBAL_SL_COOLDOWN_BARS=N, PORTFOLIO_GLOBAL_SL_STRATEGIES=csv
    _global_sl_cooldown_bars = max(0, int(os.getenv("PORTFOLIO_GLOBAL_SL_COOLDOWN_BARS", "0") or 0))
    # Supports both exact names ("alt_inplay_breakdown_v1") and short substrings ("breakdown").
    # A strategy fires the cooldown if ANY keyword in the set is a substring of its full name.
    _global_sl_strategies = _csv_set("PORTFOLIO_GLOBAL_SL_STRATEGIES")

    def _strat_matches_global(name: str) -> bool:
        n = name.lower()
        return any(kw in n for kw in _global_sl_strategies)

    _global_strat_cooldown_until_i: Dict[str, int] = {}  # keyed by full strategy name

    # ATR cache per symbol, keyed by period.
    atr_cache: Dict[str, Dict[int, List[float]]] = {s: {} for s in syms}

    def _atr(sym: str, period: int) -> List[float]:
        cache = atr_cache[sym]
        if period not in cache:
            cache[period] = _compute_atr_series(stores[sym].exec_candles, period)
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

        # Global strategy cooldown: block ALL symbols of this strategy after any SL.
        if (
            _global_sl_cooldown_bars > 0
            and ("SL" in str(reason or "").upper())
            and _strat_matches_global(strat_name)
        ):
            _global_strat_cooldown_until_i[strat_name] = i + _global_sl_cooldown_bars

        pos_by_sym.pop(sym, None)
        pos_strat.pop(sym, None)

    def _open(sym: str, sig: object, bar: Candle, *, entry_ref: float) -> bool:
        """Validate and open one position at the supplied executable price."""
        nonlocal equity

        fill_sig = copy.copy(sig)
        try:
            fill_sig.entry = float(entry_ref)
            if not bool(fill_sig.validate()):
                return False
        except Exception:
            return False

        sig_strat = str(getattr(fill_sig, "strategy", "") or "").lower()
        if (
            _global_sl_cooldown_bars > 0
            and _global_sl_strategies
            and _strat_matches_global(sig_strat)
            and _global_strat_cooldown_until_i.get(sig_strat, -1) > i
        ):
            return False

        cap = params.cap_notional_usd
        if cap is None:
            cap = (equity * float(params.leverage)) / max(1, int(params.max_positions))

        raw_sig_risk_mult = getattr(fill_sig, "risk_mult", None)
        try:
            sig_risk_mult = 1.0 if raw_sig_risk_mult is None else float(raw_sig_risk_mult)
        except (TypeError, ValueError):
            sig_risk_mult = 1.0
        sig_risk_mult = max(0.00, min(3.00, sig_risk_mult))
        if sig_risk_mult <= 0:
            return False
        risk_pct_eff = float(params.risk_pct) * sig_risk_mult
        qty = _calc_qty(equity, fill_sig, risk_pct_eff, cap)
        if qty <= 0:
            return False

        entry_px = _apply_slippage(fill_sig.entry, fill_sig.side, is_entry=True, slippage_bps=params.slippage_bps)
        entry_fee = _fees(entry_px * qty, params.fee_bps)
        equity -= entry_fee

        legacy_tp = getattr(fill_sig, "tp", 0.0)
        tps = list(getattr(fill_sig, "tps", []) or [])
        if not tps:
            tps = [float(legacy_tp)] if legacy_tp and legacy_tp > 0 else []
        fracs = list(getattr(fill_sig, "tp_fracs", []) or [])
        if not fracs and tps:
            fracs = [1.0] if len(tps) == 1 else [1.0 / len(tps)] * len(tps)
        if fracs and sum(fracs) > 1.0:
            total = sum(fracs)
            fracs = [x / total for x in fracs]

        if not tps:
            tp_qty_remaining: List[float] = []
        elif len(tps) == 1 and (not fracs or fracs[0] >= 0.999):
            tp_qty_remaining = [qty]
        else:
            tp_qty_remaining = [
                max(0.0, qty * float(fracs[k] if k < len(fracs) else 0.0))
                for k in range(len(tps))
            ]

        reason = (getattr(fill_sig, "reason", "") or "").strip()
        p = Position(
            side=fill_sig.side,
            entry_price=entry_px,
            sl=float(fill_sig.sl),
            qty=qty,
            remaining_qty=qty,
            entry_ts=bar.ts,
            entry_i=i,
            initial_sl=float(fill_sig.sl),
            equity_at_entry=equity + entry_fee,
            tps=[float(x) for x in tps],
            tp_qty_remaining=tp_qty_remaining,
            trailing_atr_mult=float(getattr(fill_sig, "trailing_atr_mult", 0.0) or 0.0),
            trailing_atr_period=int(getattr(fill_sig, "trailing_atr_period", 14) or 14),
            trail_activate_rr=float(getattr(fill_sig, "trail_activate_rr", 0.0) or 0.0),
            trail_armed=float(getattr(fill_sig, "trail_activate_rr", 0.0) or 0.0) <= 0.0,
            be_trigger_rr=float(getattr(fill_sig, "be_trigger_rr", 0.0) or 0.0),
            be_lock_rr=float(getattr(fill_sig, "be_lock_rr", 0.0) or 0.0),
            time_stop_bars=int(getattr(fill_sig, "time_stop_bars", 0) or 0),
            hh_since_entry=entry_px,
            ll_since_entry=entry_px,
            reasons=[reason] if reason else [],
            entry_fee=entry_fee,
        )
        pos_by_sym[sym] = p
        pos_strat[sym] = str(getattr(fill_sig, "strategy", "unknown"))
        return True

    def _is_limit_signal(sig: object) -> bool:
        return str(getattr(sig, "entry_order_type", "") or "").strip().lower() == "limit"

    def _limit_fillable(sig: object, bar: Candle) -> bool:
        try:
            entry = float(getattr(sig, "entry"))
        except (TypeError, ValueError):
            return False
        side = str(getattr(sig, "side", "") or "").lower()
        if side == "long":
            return float(bar.l) <= entry
        if side == "short":
            return float(bar.h) >= entry
        return False

    def _limit_expired(signal_i: int, sig: object) -> bool:
        try:
            validity = int(getattr(sig, "limit_validity_bars", 1) or 1)
        except (TypeError, ValueError):
            validity = 1
        validity = max(1, validity)
        return (i - int(signal_i)) > validity

    for i in range(min_len):
        # Advance all stores to the same index.
        for s in syms:
            stores[s].set_index(i)

        # Fill signals from the previous bar at this bar's open. Positions are
        # created before exit processing so this bar's full OHLC is considered;
        # if both TP and SL are reachable, the conservative SL-first rule wins.
        if params.entry_on_next_open and pending_signals:
            for sym in syms:
                pending = pending_signals.pop(sym, None)
                if pending is None:
                    continue
                signal_i, sig = pending
                if signal_i >= i or sym in pos_by_sym:
                    continue
                if len(pos_by_sym) >= int(params.max_positions):
                    if _is_limit_signal(sig) and not _limit_expired(signal_i, sig):
                        pending_signals[sym] = pending
                    continue
                if int(cooldown_until_i.get(sym, -1)) > i:
                    if _is_limit_signal(sig) and not _limit_expired(signal_i, sig):
                        pending_signals[sym] = pending
                    continue
                bar = stores[sym].exec_candles[i]
                if _is_limit_signal(sig):
                    if _limit_expired(signal_i, sig):
                        continue
                    if _limit_fillable(sig, bar):
                        _open(sym, sig, bar, entry_ref=float(getattr(sig, "entry")))
                    else:
                        pending_signals[sym] = pending
                else:
                    _open(sym, sig, bar, entry_ref=float(bar.o))

        # 1) Manage exits for all open positions first.
        for sym in list(pos_by_sym.keys()):
            p = pos_by_sym[sym]
            bar = stores[sym].exec_candles[i]

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

            # Volume-fade early exit (owner setup A). Closes the remaining runner
            # when impulse volume dies (vs run-up / vs peak) and price has stalled.
            if (
                _vol_exit_enable
                and p.remaining_qty > 1e-12
                and (not _vol_exit_strats or any(k in pos_strat.get(sym, "").lower() for k in _vol_exit_strats))
            ):
                _vtail = stores[sym].exec_candles[max(0, i - _vol_exit_bars):i + 1]
                _vrows = [[c.ts, c.o, c.h, c.l, c.c, c.v] for c in _vtail]
                _vfx = _volume_fade_exit(
                    _vrows,
                    side=p.side,
                    baseline_window=_vol_exit_baseline,
                    impulse_window=_vol_exit_impulse,
                    fade_ratio=_vol_exit_fade,
                    peak_fade_ratio=_vol_exit_peakfade,
                    require_stall=_vol_exit_stall,
                )
                if _vfx.get("exit"):
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
                    reason = "+".join(p.reasons + ["VOL_FADE"]) if p.reasons else "VOL_FADE"
                    _close(sym, p, bar.ts, reason)
                    continue

            # Move SL to break-even only after full-bar processing (conservative).
            if i > p.entry_i and p.be_trigger_rr > 0 and not p.be_armed:
                risk = abs(float(p.entry_price) - float(p.initial_sl))
                if risk > 0:
                    if p.side == "long":
                        be_hit = float(bar.h) >= (float(p.entry_price) + float(p.be_trigger_rr) * risk)
                        if be_hit:
                            be_sl = float(p.entry_price) + float(p.be_lock_rr) * risk
                            if be_sl > p.sl:
                                p.sl = be_sl
                            p.be_armed = True
                    else:
                        be_hit = float(bar.l) <= (float(p.entry_price) - float(p.be_trigger_rr) * risk)
                        if be_hit:
                            be_sl = float(p.entry_price) - float(p.be_lock_rr) * risk
                            if be_sl < p.sl:
                                p.sl = be_sl
                            p.be_armed = True

            # Update trailing stop after processing exits on this bar.
            if p.trailing_atr_mult > 0:
                trail_ready = bool(getattr(p, "trail_armed", False) or float(getattr(p, "trail_activate_rr", 0.0) or 0.0) <= 0.0)
                if not trail_ready and i > p.entry_i:
                    risk = abs(float(p.entry_price) - float(p.initial_sl))
                    trig_rr = float(getattr(p, "trail_activate_rr", 0.0) or 0.0)
                    if risk > 0 and trig_rr > 0:
                        if p.side == "long":
                            trail_hit = float(bar.h) >= (float(p.entry_price) + trig_rr * risk)
                        else:
                            trail_hit = float(bar.l) <= (float(p.entry_price) - trig_rr * risk)
                        if trail_hit:
                            p.trail_armed = True
                if trail_ready:
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
                bar = store.exec_candles[i]
                signal_ts = int(bar.ts) + int(getattr(store, "base_interval_min", 5)) * 60_000
                sig = selector(sym, store, signal_ts, bar.c)
                if inspect.isawaitable(sig):
                    sig = _run_awaitable(sig)
                if sig is None:
                    continue

                if params.entry_on_next_open:
                    pending_signals[sym] = (i, sig)
                    continue
                _open(sym, sig, bar, entry_ref=float(getattr(sig, "entry", bar.c)))

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
