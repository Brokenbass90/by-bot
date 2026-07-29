"""Causal execution harness for FX/CFD V2 trade plans.

Key differences from the legacy engines:

* a closed-bar signal can only fill on a later bar;
* limit orders must actually trade and expire;
* structural stop/target prices from the strategy are respected;
* stop gaps fill at the adverse open, never at an optimistic -1R;
* spread, commission, slippage and financing are explicit in price bps;
* unique event ids prevent repeated-signal storms.

Research only.  This module has no broker imports.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Sequence

from bot.fx_contracts import FxBacktestResult, FxExecutionCosts, FxTradePlan
from bot.fx_calendar import session_labels
from bot.market_context import CLOSE, HIGH, LOW, OPEN, TS, atr
from bot.news_session_filter import entry_allowed


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _seconds(ts: float) -> int:
    value = int(float(ts))
    return value // 1000 if value > 10_000_000_000 else value


def _cost_r(
    costs: FxExecutionCosts,
    *,
    entry_type: str,
    risk_frac: float,
    duration_days: float,
    side: str,
) -> tuple[float, float]:
    # The synthetic bid/ask path already pays the spread in executable prices.
    bps = costs.non_spread_bps(entry_type)
    financing_cashflow = (
        max(0.0, duration_days) * costs.financing_cashflow_bps_per_day(side)
    )
    # Positive broker cashflow reduces total cost; a debit increases it.
    bps -= financing_cashflow
    return bps, (bps / 1e4) / max(1e-12, risk_frac)


def _quote(mid: float, quote_side: str, costs: FxExecutionCosts) -> float:
    half = max(0.0, float(costs.spread_bps)) / 2.0 / 1e4
    return float(mid) * (1.0 - half if quote_side == "bid" else 1.0 + half)


def _fill_time_allowed(
    plan: FxTradePlan,
    *,
    ts: int,
    price: float,
    news_events: Optional[Sequence[Dict[str, Any]]],
) -> bool:
    if ts < int(plan.event.signal_ts):
        return False
    if plan.allowed_fill_sessions:
        for checkpoint in (ts, ts + int(plan.execution_bar_seconds) - 1):
            if not set(session_labels(checkpoint)).intersection(plan.allowed_fill_sessions):
                return False
    if news_events is not None:
        checkpoints = (
            ts,
            ts + int(plan.execution_bar_seconds) // 2,
            ts + int(plan.execution_bar_seconds) - 1,
        )
        for checkpoint in checkpoints:
            gate = entry_allowed(
                checkpoint, events=news_events, price=price,
                avoid_low_liq_session=False,
            )
            if not gate.allow:
                return False
    return True


def _resolve_exit(
    rows: Sequence[Sequence[float]],
    *,
    fill_i: int,
    entry: float,
    stop: float,
    target: float,
    side: str,
    fill_at_open: bool,
    costs: FxExecutionCosts,
    max_hold_bars: int,
) -> Dict[str, Any]:
    end = min(len(rows) - 1, fill_i + max(1, int(max_hold_bars)) - 1)
    risk = (entry - stop) if side == "long" else (stop - entry)
    best = worst = 0.0
    for j in range(fill_i, end + 1):
        quote_side = "bid" if side == "long" else "ask"
        o = _quote(_f(rows[j], OPEN), quote_side, costs)
        h = _quote(_f(rows[j], HIGH), quote_side, costs)
        l = _quote(_f(rows[j], LOW), quote_side, costs)
        # A resting limit that is first touched intrabar did not exist as a
        # position at this bar's open.  H1 OHLC cannot tell whether the bar's
        # favourable extreme happened before or after that touch, so the fill
        # bar may stop us out but may never award a same-bar target.  Orders
        # marketable at the open use the actual open and normal SL-first logic.
        intrabar_limit_fill = j == fill_i and not fill_at_open
        apply_open_gap = not intrabar_limit_fill
        if side == "long":
            if not intrabar_limit_fill:
                best = max(best, (h - entry) / risk)
            worst = min(worst, (l - entry) / risk)
            # Gap through the stop is paid at the adverse open.
            if apply_open_gap and o <= stop:
                return {"exit_i": j, "exit": o, "reason": "SL_GAP", "mfe_r": best, "mae_r": worst}
            if apply_open_gap and o >= target:
                return {"exit_i": j, "exit": target, "reason": "TP_GAP", "mfe_r": best, "mae_r": worst}
            if l <= stop:
                return {"exit_i": j, "exit": stop, "reason": "SL", "mfe_r": best, "mae_r": worst}
            if not intrabar_limit_fill and h >= target:
                return {"exit_i": j, "exit": target, "reason": "TP", "mfe_r": best, "mae_r": worst}
        else:
            if not intrabar_limit_fill:
                best = max(best, (entry - l) / risk)
            worst = min(worst, (entry - h) / risk)
            if apply_open_gap and o >= stop:
                return {"exit_i": j, "exit": o, "reason": "SL_GAP", "mfe_r": best, "mae_r": worst}
            if apply_open_gap and o <= target:
                return {"exit_i": j, "exit": target, "reason": "TP_GAP", "mfe_r": best, "mae_r": worst}
            if h >= stop:
                return {"exit_i": j, "exit": stop, "reason": "SL", "mfe_r": best, "mae_r": worst}
            if not intrabar_limit_fill and l <= target:
                return {"exit_i": j, "exit": target, "reason": "TP", "mfe_r": best, "mae_r": worst}
    return {
        "exit_i": end,
        "exit": _quote(
            _f(rows[end], CLOSE), "bid" if side == "long" else "ask", costs
        ),
        "reason": "TIME",
        "mfe_r": best,
        "mae_r": worst,
    }


def _fill_plan(
    rows: Sequence[Sequence[float]],
    *,
    signal_i: int,
    plan: FxTradePlan,
    atr_value: float,
    costs: FxExecutionCosts,
    news_events: Optional[Sequence[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    if signal_i + 1 >= len(rows):
        return None
    if plan.entry_type == "market_next_open":
        j = signal_i + 1
        mid_open = _f(rows[j], OPEN)
        if not _fill_time_allowed(
            plan,
            ts=_seconds(_f(rows[j], TS)),
            price=mid_open,
            news_events=news_events,
        ):
            return {"blocked_fill": True}
        entry = _quote(mid_open, "ask" if plan.side == "long" else "bid", costs)
        if not (entry == entry and entry > 0):
            return None
        gap_atr = abs(entry - plan.reference_price) / max(1e-12, atr_value)
        if gap_atr > plan.max_entry_gap_atr:
            return {"skipped_gap": True, "gap_atr": gap_atr}
        return {
            "fill_i": j,
            "entry": entry,
            "wait_bars": 1,
            "gap_atr": gap_atr,
            "fill_at_open": True,
        }

    limit = float(plan.limit_price or 0.0)
    last = min(len(rows) - 1, signal_i + int(plan.validity_bars))
    for j in range(signal_i + 1, last + 1):
        mid_open = _f(rows[j], OPEN)
        if not _fill_time_allowed(
            plan,
            ts=_seconds(_f(rows[j], TS)),
            price=mid_open,
            news_events=news_events,
        ):
            continue
        entry_quote = "ask" if plan.side == "long" else "bid"
        open_price = _quote(mid_open, entry_quote, costs)
        low_price = _quote(_f(rows[j], LOW), entry_quote, costs)
        high_price = _quote(_f(rows[j], HIGH), entry_quote, costs)
        marketable_at_open = (
            open_price <= limit if plan.side == "long" else open_price >= limit
        )
        touched = marketable_at_open or (
            low_price <= limit
            if plan.side == "long"
            else high_price >= limit
        )
        if touched:
            entry = open_price if marketable_at_open else limit
            gap_atr = abs(entry - plan.reference_price) / max(1e-12, atr_value)
            if gap_atr > plan.max_entry_gap_atr:
                return {"skipped_gap": True, "gap_atr": gap_atr}
            return {
                "fill_i": j,
                "entry": entry,
                "wait_bars": j - signal_i,
                "gap_atr": gap_atr,
                "fill_at_open": marketable_at_open,
            }
    if last < signal_i + int(plan.validity_bars):
        return {"censored_order": True}
    return None


def backtest_fx_plan_strategy(
    rows: Sequence[Sequence[float]],
    strategy_fn: Callable[[Sequence[Sequence[float]]], Optional[FxTradePlan]],
    *,
    costs: FxExecutionCosts,
    warmup: int = 300,
    context_bars: int = 320,
    cooldown_bars: int = 2,
    min_structural_rr: float = 1.0,
    news_events: Optional[Sequence[Dict[str, Any]]] = None,
) -> FxBacktestResult:
    result = FxBacktestResult()
    seen_events: set[str] = set()
    i = max(2, int(warmup))
    while i < len(rows) - 2:
        prefix = list(rows[max(0, i - int(context_bars) + 1): i + 1])
        try:
            plan = strategy_fn(prefix)
        except (ValueError, ArithmeticError):
            result.invalid_plans += 1
            i += 1
            continue
        if plan is None:
            i += 1
            continue
        result.signals += 1
        ledger = {
            "event_id": plan.event.event_id,
            "strategy": plan.strategy,
            "side": plan.side,
            "signal_ts": _seconds(plan.event.signal_ts),
            "signal_bar_ts": _seconds(_f(rows[i], TS)),
            "entry_type": plan.entry_type,
            "outcome": "detected",
        }
        result.signal_ledger.append(ledger)
        if plan.event.event_id in seen_events:
            result.duplicate_events += 1
            ledger["outcome"] = "duplicate_event"
            i += 1
            continue
        seen_events.add(plan.event.event_id)
        a = float(plan.metadata.get("atr", float("nan")))
        if not (a == a and a > 0):
            a = atr(prefix, exclude_last=True)
        if not (a == a and a > 0):
            result.invalid_plans += 1
            ledger["outcome"] = "invalid_atr"
            i += 1
            continue
        result.orders_placed += 1
        ledger["outcome"] = "order_placed"
        fill = _fill_plan(
            rows, signal_i=i, plan=plan, atr_value=a, costs=costs,
            news_events=news_events,
        )
        if fill is None:
            result.unfilled += 1
            ledger["outcome"] = "unfilled"
            i += max(1, int(plan.validity_bars) + int(cooldown_bars))
            continue
        if fill.get("blocked_fill"):
            result.blocked_fill_window += 1
            ledger["outcome"] = "blocked_fill_window"
            i += 1
            continue
        if fill.get("censored_order"):
            result.censored_orders += 1
            ledger["outcome"] = "censored_order_at_segment_end"
            i = len(rows)
            continue
        if fill.get("skipped_gap"):
            result.skipped_gap += 1
            ledger["outcome"] = "skipped_gap"
            i += 1
            continue
        fill_i, entry = int(fill["fill_i"]), float(fill["entry"])
        stop = float(plan.stop_price)
        risk = (entry - stop) if plan.side == "long" else (stop - entry)
        # A market gap through the preplanned stop invalidates the entry.
        if not (risk > 0 and entry > 0):
            result.skipped_gap += 1
            ledger["outcome"] = "invalid_gap_risk"
            i = fill_i + 1
            continue
        fallback_target = (
            entry + plan.target_rr * risk
            if plan.side == "long"
            else entry - plan.target_rr * risk
        )
        target = float(plan.target_price) if plan.target_price is not None else fallback_target
        structural_rr = (
            (target - entry) / risk
            if plan.side == "long"
            else (entry - target) / risk
        )
        if structural_rr < float(min_structural_rr):
            result.skipped_rr += 1
            ledger["outcome"] = "skipped_structural_rr"
            i = fill_i + 1
            continue

        resolved = _resolve_exit(
            rows,
            fill_i=fill_i,
            entry=entry,
            stop=stop,
            target=target,
            side=plan.side,
            fill_at_open=bool(fill.get("fill_at_open", False)),
            costs=costs,
            max_hold_bars=plan.max_hold_bars,
        )
        exit_i, exit_price = int(resolved["exit_i"]), float(resolved["exit"])
        if (
            resolved["reason"] == "TIME"
            and exit_i == len(rows) - 1
            and fill_i + int(plan.max_hold_bars) - 1 > len(rows) - 1
        ):
            result.censored_trades += 1
            ledger["outcome"] = "censored_trade_at_segment_end"
            i = len(rows)
            continue
        gross_r = (
            (exit_price - entry) / risk
            if plan.side == "long"
            else (entry - exit_price) / risk
        )
        duration_days = max(
            0.0,
            (_seconds(_f(rows[exit_i], TS)) - _seconds(_f(rows[fill_i], TS))) / 86400.0,
        )
        risk_frac = risk / entry
        cost_bps, cost_r = _cost_r(
            costs,
            entry_type=plan.entry_type,
            risk_frac=risk_frac,
            duration_days=duration_days,
            side=plan.side,
        )
        result.trades.append({
            "strategy": plan.strategy,
            "event_id": plan.event.event_id,
            "side": plan.side,
            "signal_ts": _seconds(plan.event.signal_ts),
            "entry_ts": _seconds(_f(rows[fill_i], TS)),
            "exit_ts": _seconds(_f(rows[exit_i], TS)),
            "entry_type": plan.entry_type,
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "exit_reason": resolved["reason"],
            "wait_bars": int(fill.get("wait_bars", 0)),
            "gap_atr": float(fill.get("gap_atr", 0.0)),
            "risk_frac": risk_frac,
            "duration_days": duration_days,
            "financing_cashflow_bps": round(
                duration_days
                * costs.financing_cashflow_bps_per_day(plan.side),
                6,
            ),
            "gross_r": round(gross_r, 6),
            "cost_bps": round(cost_bps, 6),
            "synthetic_spread_bps": float(costs.spread_bps),
            "quote_model": "constant_spread_bid_ask",
            "cost_r": round(cost_r, 6),
            "r": round(gross_r - cost_r, 6),
            "mfe_r": round(float(resolved["mfe_r"]), 6),
            "mae_r": round(float(resolved["mae_r"]), 6),
            "level": plan.event.level,
            "level_kind": plan.event.level_kind,
            "reason": plan.event.reason,
            "metadata": {**plan.event.metadata, **plan.metadata},
        })
        ledger.update({
            "outcome": "filled",
            "entry_ts": _seconds(_f(rows[fill_i], TS)),
            "exit_ts": _seconds(_f(rows[exit_i], TS)),
            "exit_reason": resolved["reason"],
        })
        i = exit_i + max(1, int(cooldown_bars))
    return result


def reprice_trades(trades: Sequence[Dict[str, Any]], costs: FxExecutionCosts) -> list[Dict[str, Any]]:
    """Reprice fees only; a spread change requires a complete rerun."""
    out: list[Dict[str, Any]] = []
    for source in trades:
        source_spread = float(source.get("synthetic_spread_bps", costs.spread_bps))
        if abs(source_spread - float(costs.spread_bps)) > 1e-12:
            raise ValueError("spread changes require rerunning fills and barriers")
        row = dict(source)
        bps, cr = _cost_r(
            costs,
            entry_type=str(row["entry_type"]),
            risk_frac=float(row["risk_frac"]),
            duration_days=float(row.get("duration_days", 0.0)),
            side=str(row["side"]),
        )
        row["financing_cashflow_bps"] = round(
            float(row.get("duration_days", 0.0))
            * costs.financing_cashflow_bps_per_day(str(row["side"])),
            6,
        )
        row["cost_bps"] = round(bps, 6)
        row["cost_r"] = round(cr, 6)
        row["r"] = round(float(row["gross_r"]) - cr, 6)
        out.append(row)
    return out


def summarize_fx_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rs = [float(t["r"]) for t in trades if t.get("r") is not None]
    gp = sum(x for x in rs if x > 0)
    gl = -sum(x for x in rs if x < 0)
    equity = peak = max_dd = 0.0
    exit_ordered = sorted(
        (t for t in trades if t.get("r") is not None),
        key=lambda row: (float(row.get("exit_ts", 0)), float(row.get("entry_ts", 0))),
    )
    for trade in exit_ordered:
        value = float(trade["r"])
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(rs),
        "net_r": round(sum(rs), 6),
        "pf": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0),
        "win_rate": sum(1 for x in rs if x > 0) / len(rs) if rs else 0.0,
        "closed_trade_drawdown_r": round(max_dd, 6),
        "drawdown_basis": "exit_ordered_closed_trades_not_mark_to_market",
        "avg_r": sum(rs) / len(rs) if rs else 0.0,
    }
