"""Causal daily-portfolio primitives for Alpaca research diagnostics.

This module is intentionally broker-free.  It models the deployable monthly
fractional protection path closely enough to find accounting and contract
defects, but it does not pretend that daily OHLC can reproduce a manager that
samples the market every fifteen minutes.  A caller must label results as a
daily proxy unless it supplies point-in-time membership, authoritative XNYS
sessions, corporate actions, and broker-calibrated intraday observations.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from statistics import pstdev
from typing import Mapping, Sequence

from backtest.alpaca_exact_parity_contract import DailyBar, adverse_fill_price, daily_max_drawdown


class HonestPortfolioError(ValueError):
    """Raised when a causal portfolio replay cannot be completed safely."""


@dataclass(frozen=True)
class Candidate:
    symbol: str
    score: float
    atr_at_signal: float
    atr_pct_at_signal: float
    signal_close: float
    weight: float = 0.0


@dataclass(frozen=True)
class MonthlyDecision:
    signal_session: date
    entry_session: date
    picks: tuple[Candidate, ...]
    reason: str


@dataclass
class _Position:
    symbol: str
    qty: float
    entry_fill: float
    entry_session: date
    active_stop: float
    hwm: float


@dataclass(frozen=True)
class LiveProtectionDailyProxy:
    """Daily conservative proxy of the current fractional live protection.

    The real manager samples current prices every 15 minutes.  This proxy uses
    completed daily closes for ratchet decisions, then activates a higher stop
    on the next session.  It therefore cannot claim intraday parity.
    """

    fallback_stop_pct: float = 0.05
    activate_gain_pct: float = 3.5
    trail_pct: float = 3.5
    minimum_lock_gain_pct: float = 0.5
    market_gap_bps: float = 10.0
    reentry_block_calendar_days: int = 21
    initial_stop_anchor: str = "signal_close"
    maximum_positive_entry_gap_pct: float | None = None


def _finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0


def quantize_sell_stop(price: float) -> float:
    """Use Alpaca's current equity stop grid and never round a sell stop up."""

    if not _finite_positive(price):
        raise HonestPortfolioError("stop price must be positive and finite")
    value = Decimal(str(price))
    quantum = Decimal("0.01") if value >= Decimal("1") else Decimal("0.0001")
    return float(value.quantize(quantum, rounding=ROUND_DOWN))


def capped_normalized_weights(
    raw_weights: Mapping[str, float], *, maximum_weight: float
) -> dict[str, float]:
    """Normalize positive weights while enforcing a true per-name hard cap.

    If too few names exist to invest the whole sleeve without breaking the cap,
    the remainder stays in cash.  This deliberately avoids the old cap-then-
    renormalize bug that could silently re-breach the stated limit.
    """

    if not 0 < maximum_weight <= 1:
        raise HonestPortfolioError("maximum_weight must be in (0, 1]")
    clean = {
        str(symbol): float(value)
        for symbol, value in raw_weights.items()
        if str(symbol) and math.isfinite(float(value)) and float(value) > 0
    }
    if not clean:
        return {}
    result = {symbol: 0.0 for symbol in clean}
    remaining = set(clean)
    remaining_mass = min(1.0, len(clean) * maximum_weight)
    while remaining and remaining_mass > 1e-12:
        raw_total = sum(clean[symbol] for symbol in remaining)
        if raw_total <= 0:
            break
        capped_now: list[str] = []
        for symbol in sorted(remaining):
            proposed = remaining_mass * clean[symbol] / raw_total
            if proposed >= maximum_weight - 1e-12:
                result[symbol] = maximum_weight
                capped_now.append(symbol)
        if not capped_now:
            for symbol in remaining:
                result[symbol] = remaining_mass * clean[symbol] / raw_total
            remaining_mass = 0.0
            break
        for symbol in capped_now:
            remaining.remove(symbol)
            remaining_mass -= maximum_weight
    return result


def _returns(bars: Sequence[DailyBar], lookback: int) -> dict[date, float]:
    out: dict[date, float] = {}
    start = max(1, len(bars) - lookback)
    for index in range(start, len(bars)):
        previous = bars[index - 1].close
        if previous > 0:
            out[bars[index].session_date] = bars[index].close / previous - 1.0
    return out


def _correlation(left: Sequence[DailyBar], right: Sequence[DailyBar], lookback: int) -> float | None:
    left_returns = _returns(left, lookback)
    right_returns = _returns(right, lookback)
    overlap = sorted(set(left_returns).intersection(right_returns))
    if len(overlap) < max(10, lookback // 3):
        return None
    xs = [left_returns[session] for session in overlap]
    ys = [right_returns[session] for session in overlap]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x <= 0 or variance_y <= 0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def _atr20(bars: Sequence[DailyBar]) -> float:
    if len(bars) < 21:
        return float("nan")
    values: list[float] = []
    for index in range(len(bars) - 20, len(bars)):
        row = bars[index]
        previous_close = bars[index - 1].close
        values.append(max(row.high - row.low, abs(row.high - previous_close), abs(row.low - previous_close)))
    return sum(values) / len(values)


def _universe_health(bars: Sequence[DailyBar], lookback: int = 80) -> float:
    if len(bars) < max(lookback + 1, 61):
        return float("nan")
    close = bars[-1].close
    start_close = bars[-lookback - 1].close
    if not (_finite_positive(close) and _finite_positive(start_close)):
        return float("nan")
    momentum = close / start_close - 1.0
    recent_high = max(row.high for row in bars[-lookback:])
    drawdown = close / recent_high - 1.0
    closes = [row.close for row in bars]
    sma20 = sum(closes[-20:]) / 20.0
    sma60 = sum(closes[-60:]) / 60.0
    volatility = pstdev(list(_returns(bars, lookback).values()))
    return (
        1.35 * momentum
        + 0.45 * (close / sma20 - 1.0)
        + 0.35 * (close / sma60 - 1.0)
        - 0.90 * abs(min(0.0, drawdown))
        - 2.20 * volatility
    )


def _v38_candidate(symbol: str, bars: Sequence[DailyBar]) -> Candidate | None:
    lookback = 28
    if len(bars) < max(lookback + 5, 61):
        return None
    closes = [row.close for row in bars]
    close = closes[-1]
    sma20 = sum(closes[-20:]) / 20.0
    sma28 = sum(closes[-lookback:]) / lookback
    momentum20 = close / closes[-20] - 1.0
    momentum28 = close / closes[-lookback] - 1.0
    high28 = max(row.high for row in bars[-lookback:])
    pullback = close / high28 - 1.0
    returns20 = list(_returns(bars, 20).values())
    volatility20 = pstdev(returns20) if len(returns20) >= 5 else 0.0
    atr = _atr20(bars)
    if not _finite_positive(atr):
        return None
    if close < sma28 or momentum28 <= 0.05 or not -0.12 <= pullback <= -0.015:
        return None
    score = (
        1.20 * momentum28
        + 0.60 * momentum20
        - 0.35 * abs(pullback)
        - 2.50 * volatility20
        + (0.02 if close > sma20 else -0.02)
    )
    return Candidate(symbol, score, atr, atr / close * 100.0, close)


def select_v38_successor(
    history: Mapping[str, Sequence[DailyBar]],
    *,
    sectors: Mapping[str, str],
    clusters: Sequence[set[str]],
    universe_top_k: int = 18,
    top_n: int = 4,
    maximum_weight: float = 0.60,
) -> tuple[Candidate, ...]:
    """Select the frozen v38 successor intent from completed signal bars."""

    health = {
        symbol: _universe_health(bars)
        for symbol, bars in history.items()
        if symbol not in {"SPY", "QQQ"}
    }
    eligible = {
        symbol
        for symbol, _score in sorted(
            ((symbol, score) for symbol, score in health.items() if math.isfinite(score)),
            key=lambda item: item[1],
            reverse=True,
        )[:universe_top_k]
    }
    candidates = [
        candidate
        for symbol in eligible
        if (candidate := _v38_candidate(symbol, history[symbol])) is not None
    ]
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    selected: list[Candidate] = []
    sector_counts: dict[str, int] = {}
    cluster_counts = [0 for _ in clusters]
    remaining = list(candidates)
    while remaining and len(selected) < top_n:
        best_index: int | None = None
        best_adjusted = float("-inf")
        for index, candidate in enumerate(remaining):
            sector = sectors.get(candidate.symbol, "unknown")
            if sector_counts.get(sector, 0) >= 2:
                continue
            member_clusters = [i for i, group in enumerate(clusters) if candidate.symbol in group]
            if any(cluster_counts[i] >= 1 for i in member_clusters):
                continue
            penalty = 0.0
            blocked = False
            for existing in selected:
                corr = _correlation(history[candidate.symbol], history[existing.symbol], 60)
                if corr is None:
                    continue
                if corr >= 0.75:
                    blocked = True
                    break
                penalty += max(0.0, corr - 0.50)
            adjusted = candidate.score - 2.5 * penalty
            if not blocked and adjusted > best_adjusted:
                best_index = index
                best_adjusted = adjusted
        if best_index is None:
            break
        picked = remaining.pop(best_index)
        selected.append(picked)
        sector = sectors.get(picked.symbol, "unknown")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        for index, group in enumerate(clusters):
            if picked.symbol in group:
                cluster_counts[index] += 1
    raw = {
        candidate.symbol: max(0.001, candidate.score) / max(0.5, math.sqrt(candidate.atr_pct_at_signal))
        for candidate in selected
    }
    weights = capped_normalized_weights(raw, maximum_weight=maximum_weight)
    return tuple(
        Candidate(
            candidate.symbol,
            candidate.score,
            candidate.atr_at_signal,
            candidate.atr_pct_at_signal,
            candidate.signal_close,
            weights.get(candidate.symbol, 0.0),
        )
        for candidate in selected
    )


def _bar_map(data: Mapping[str, Sequence[DailyBar]]) -> dict[str, dict[date, DailyBar]]:
    out: dict[str, dict[date, DailyBar]] = {}
    for symbol, rows in data.items():
        dates = [row.session_date for row in rows]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise HonestPortfolioError(f"{symbol}: bars must be unique and ordered")
        out[symbol] = {row.session_date: row for row in rows}
    return out


def simulate_live_protection_daily_proxy(
    data: Mapping[str, Sequence[DailyBar]],
    sessions: Sequence[date],
    decisions: Sequence[MonthlyDecision],
    *,
    initial_capital: float = 1_000.0,
    target_gross_exposure: float = 0.70,
    cost_bps_per_side: float = 5.0,
    policy: LiveProtectionDailyProxy = LiveProtectionDailyProxy(),
) -> dict[str, object]:
    """Replay monthly selections as one causal, cash-aware daily portfolio."""

    if not _finite_positive(initial_capital):
        raise HonestPortfolioError("initial capital must be positive")
    if not 0 <= target_gross_exposure <= 1:
        raise HonestPortfolioError("target gross exposure must be in [0, 1]")
    if list(sessions) != sorted(set(sessions)):
        raise HonestPortfolioError("sessions must be unique and ordered")
    if policy.initial_stop_anchor not in {"signal_close", "entry_fill"}:
        raise HonestPortfolioError("initial_stop_anchor must be signal_close or entry_fill")
    if (
        policy.maximum_positive_entry_gap_pct is not None
        and policy.maximum_positive_entry_gap_pct < 0
    ):
        raise HonestPortfolioError("maximum_positive_entry_gap_pct must be non-negative")
    bars_by_symbol = _bar_map(data)
    decision_by_entry = {decision.entry_session: decision for decision in decisions}
    if len(decision_by_entry) != len(decisions):
        raise HonestPortfolioError("entry sessions must be unique")

    cash = float(initial_capital)
    positions: dict[str, _Position] = {}
    reentry_block_until: dict[str, date] = {}
    equity_rows: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []

    def close_position(position: _Position, session: date, reference: float, reason: str) -> None:
        nonlocal cash
        fill = adverse_fill_price(reference, side="sell", cost_bps=cost_bps_per_side)
        proceeds = position.qty * fill
        cash += proceeds
        pnl = proceeds - position.qty * position.entry_fill
        trades.append(
            {
                "symbol": position.symbol,
                "entry_session": position.entry_session.isoformat(),
                "exit_session": session.isoformat(),
                "entry_fill": position.entry_fill,
                "exit_fill": fill,
                "qty": position.qty,
                "pnl": pnl,
                "return_pct": (fill / position.entry_fill - 1.0) * 100.0,
                "reason": reason,
            }
        )
        del positions[position.symbol]
        if reason.startswith("protective_stop"):
            reentry_block_until[position.symbol] = session + timedelta(days=policy.reentry_block_calendar_days)

    for session in sessions:
        decision = decision_by_entry.get(session)
        if decision is not None:
            selected = {candidate.symbol: candidate for candidate in decision.picks}
            # Stale positions are closed at the next session open.  Positions
            # retained by the new selection are held without a fictional
            # liquidation/re-entry or reset of their protection state.
            for symbol in sorted(set(positions) - set(selected)):
                bar = bars_by_symbol.get(symbol, {}).get(session)
                if bar is None:
                    raise HonestPortfolioError(f"{symbol}: missing stale-close bar on {session}")
                close_position(positions[symbol], session, bar.open, "monthly_rotation_next_open")

            open_equity = cash
            for position in positions.values():
                bar = bars_by_symbol.get(position.symbol, {}).get(session)
                if bar is None:
                    raise HonestPortfolioError(f"{position.symbol}: missing open mark on {session}")
                open_equity += position.qty * bar.open

            bought: list[str] = []
            blocked: list[str] = []
            gap_blocked: list[str] = []
            for candidate in decision.picks:
                if candidate.symbol in positions:
                    continue
                if session < reentry_block_until.get(candidate.symbol, date.min):
                    blocked.append(candidate.symbol)
                    continue
                bar = bars_by_symbol.get(candidate.symbol, {}).get(session)
                if bar is None:
                    raise HonestPortfolioError(f"{candidate.symbol}: missing entry bar on {session}")
                positive_gap_pct = (bar.open / candidate.signal_close - 1.0) * 100.0
                if (
                    policy.maximum_positive_entry_gap_pct is not None
                    and positive_gap_pct > policy.maximum_positive_entry_gap_pct
                ):
                    blocked.append(candidate.symbol)
                    gap_blocked.append(candidate.symbol)
                    continue
                requested = open_equity * target_gross_exposure * max(0.0, candidate.weight)
                notional = min(cash, requested)
                if notional <= 0:
                    continue
                entry_fill = adverse_fill_price(bar.open, side="buy", cost_bps=cost_bps_per_side)
                qty = notional / entry_fill
                cash -= qty * entry_fill
                stop_anchor = (
                    entry_fill if policy.initial_stop_anchor == "entry_fill"
                    else candidate.signal_close
                )
                signal_stop = stop_anchor - 2.0 * candidate.atr_at_signal
                fallback_stop = entry_fill * (1.0 - policy.fallback_stop_pct)
                initial_stop = quantize_sell_stop(signal_stop if signal_stop > 0 else fallback_stop)
                positions[candidate.symbol] = _Position(
                    candidate.symbol,
                    qty,
                    entry_fill,
                    session,
                    initial_stop,
                    entry_fill,
                )
                bought.append(candidate.symbol)
            decision_rows.append(
                {
                    "signal_session": decision.signal_session.isoformat(),
                    "entry_session": session.isoformat(),
                    "reason": decision.reason,
                    "selected": sorted(selected),
                    "bought": bought,
                    "reentry_blocked": blocked,
                    "gap_blocked": gap_blocked,
                }
            )

        for symbol in sorted(list(positions)):
            position = positions.get(symbol)
            if position is None:
                continue
            bar = bars_by_symbol.get(symbol, {}).get(session)
            if bar is None:
                raise HonestPortfolioError(f"{symbol}: missing held-position bar on {session}")
            if session == position.entry_session and bar.open <= position.active_stop:
                close_position(position, session, bar.open, "entry_gap_below_signal_stop")
                continue
            if session > position.entry_session and bar.open <= position.active_stop:
                close_position(position, session, bar.open, "protective_stop_gap_open")
                continue
            if bar.low <= position.active_stop:
                close_position(position, session, position.active_stop, "protective_stop_intraday")
                continue

            # The daily proxy samples the completed close.  A resulting ratchet
            # is deliberately not allowed to fire on the same OHLC bar.
            position.hwm = max(position.hwm, bar.close)
            peak_gain_pct = (position.hwm / position.entry_fill - 1.0) * 100.0
            if peak_gain_pct + 1e-12 >= policy.activate_gain_pct:
                trail_floor = position.hwm * (1.0 - policy.trail_pct / 100.0)
                locked_floor = position.entry_fill * (1.0 + policy.minimum_lock_gain_pct / 100.0)
                market_ceiling = bar.close * (1.0 - policy.market_gap_bps / 10_000.0)
                target = min(max(position.active_stop, trail_floor, locked_floor), market_ceiling)
                if target > position.active_stop:
                    position.active_stop = quantize_sell_stop(target)

        open_value = 0.0
        for position in positions.values():
            bar = bars_by_symbol.get(position.symbol, {}).get(session)
            if bar is None:
                raise HonestPortfolioError(f"{position.symbol}: missing close mark on {session}")
            open_value += position.qty * bar.close
        equity = cash + open_value
        equity_rows.append(
            {
                "session": session.isoformat(),
                "equity": equity,
                "cash": cash,
                "gross_exposure": open_value / equity if equity > 0 else 0.0,
                "positions": sorted(positions),
            }
        )

    daily_equity = [float(row["equity"]) for row in equity_rows]
    final_equity = daily_equity[-1] if daily_equity else initial_capital
    wins = sum(float(row["pnl"]) for row in trades if float(row["pnl"]) > 0)
    losses = -sum(float(row["pnl"]) for row in trades if float(row["pnl"]) < 0)
    month_end: dict[str, float] = {}
    for row in equity_rows:
        month_end[str(row["session"])[:7]] = float(row["equity"])
    previous = initial_capital
    monthly_returns: list[float] = []
    for _month, value in sorted(month_end.items()):
        monthly_returns.append(value / previous - 1.0)
        previous = value
    return {
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "return_pct": (final_equity / initial_capital - 1.0) * 100.0,
        "daily_max_drawdown_pct": -daily_max_drawdown(initial_capital, daily_equity) * 100.0,
        "profit_factor_realized": wins / losses if losses > 0 else (math.inf if wins > 0 else 0.0),
        "realized_trades": len(trades),
        "red_months": sum(value < 0 for value in monthly_returns),
        "months": len(monthly_returns),
        "worst_month_pct": min(monthly_returns, default=0.0) * 100.0,
        "average_gross_exposure_pct": (
            sum(float(row["gross_exposure"]) for row in equity_rows) / max(1, len(equity_rows)) * 100.0
        ),
        "daily_equity": equity_rows,
        "trades": trades,
        "decisions": decision_rows,
    }
