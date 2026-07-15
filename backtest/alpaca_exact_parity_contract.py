"""Research-only primitives for an exact Alpaca monthly parity replay.

The module deliberately has no broker, environment, network, order, or live
configuration imports.  It turns an already verified XNYS session ledger into
signal/fill pairs and freezes the causal daily-bar mechanics shared by every
research arm.  A performance runner must not use it until the separate parity
preflight has accepted every point-in-time input.
"""
from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SHA256_HEX_LENGTH = 64


class ParityContractError(ValueError):
    """Raised when a parity input or causal ordering rule is invalid."""


@dataclass(frozen=True)
class XNYSSession:
    session_date: date
    market_open_utc: datetime
    market_close_utc: datetime
    source_record_sha256: str


@dataclass(frozen=True)
class DailyBar:
    session_date: date
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SharedExitContract:
    initial_stop_atr: float = 2.0
    profit_target_atr: float = 3.2
    break_even_trigger_r: float = 0.8
    trail_atr: float = 1.5
    max_hold_sessions: int = 22
    intramonth_portfolio_stop_pct: float = 0.08
    same_bar_stop_and_target: str = "stop_first"
    stop_update_timing: str = "completed_bar_for_next_session"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == SHA256_HEX_LENGTH and all(ch in "0123456789abcdef" for ch in text)


def _parse_utc(value: object, *, field: str) -> datetime:
    text = str(value or "")
    if not text.endswith("Z"):
        raise ParityContractError(f"{field} must be an explicit UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ParityContractError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo != timezone.utc:
        raise ParityContractError(f"{field} must be UTC")
    return parsed


def load_xnys_session_ledger(path: Path, *, expected_sha256: str) -> list[XNYSSession]:
    """Load a hash-pinned authoritative session ledger.

    Required CSV grain: one row per XNYS session.  This function validates the
    ledger shape and chronology; it does *not* infer holidays from price bars.
    """

    if not path.is_file():
        raise ParityContractError("XNYS session ledger is missing")
    if not _is_sha256(expected_sha256) or sha256_file(path) != expected_sha256:
        raise ParityContractError("XNYS session ledger hash mismatch")
    required = {
        "session_date",
        "market_open_utc",
        "market_close_utc",
        "source_record_sha256",
    }
    sessions: list[XNYSSession] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) != required:
            raise ParityContractError("XNYS session ledger columns changed")
        for row_no, row in enumerate(reader, start=2):
            try:
                session_date = date.fromisoformat(str(row["session_date"]))
            except (TypeError, ValueError) as exc:
                raise ParityContractError(f"invalid session_date at row {row_no}") from exc
            market_open = _parse_utc(row["market_open_utc"], field="market_open_utc")
            market_close = _parse_utc(row["market_close_utc"], field="market_close_utc")
            source_sha = str(row["source_record_sha256"] or "")
            if not _is_sha256(source_sha):
                raise ParityContractError(f"source_record_sha256 invalid at row {row_no}")
            if market_open >= market_close:
                raise ParityContractError(f"open must precede close at row {row_no}")
            if market_open.date() != session_date or market_close.date() != session_date:
                raise ParityContractError(f"UTC open/close date disagrees with session_date at row {row_no}")
            sessions.append(XNYSSession(session_date, market_open, market_close, source_sha))
    if len(sessions) < 2:
        raise ParityContractError("XNYS session ledger needs at least two sessions")
    dates = [row.session_date for row in sessions]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ParityContractError("XNYS sessions must be unique and strictly increasing")
    return sessions


def calendar_month_signal_schedule(sessions: Sequence[XNYSSession]) -> list[dict[str, str]]:
    """Map each completed calendar-month close to the next XNYS open.

    The last observed month is omitted when its successor session is not in the
    ledger.  That prevents an inferred/future fill date from leaking in.
    """

    if len(sessions) < 2:
        raise ParityContractError("schedule requires at least two sessions")
    dates = [row.session_date for row in sessions]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ParityContractError("schedule sessions must be unique and ordered")
    month_last_index: dict[str, int] = {}
    for index, row in enumerate(sessions):
        month_last_index[row.session_date.strftime("%Y-%m")] = index
    schedule: list[dict[str, str]] = []
    for month, index in sorted(month_last_index.items()):
        if index + 1 >= len(sessions):
            continue
        signal = sessions[index]
        entry = sessions[index + 1]
        if entry.session_date.strftime("%Y-%m") == month:
            raise ParityContractError("month-end selection is internally inconsistent")
        schedule.append(
            {
                "signal_month": month,
                "signal_session": signal.session_date.isoformat(),
                "signal_at_utc": signal.market_close_utc.isoformat().replace("+00:00", "Z"),
                "entry_session": entry.session_date.isoformat(),
                "entry_at_utc": entry.market_open_utc.isoformat().replace("+00:00", "Z"),
            }
        )
    if not schedule:
        raise ParityContractError("session ledger does not contain a complete month plus successor")
    return schedule


def daily_next_open_schedule(sessions: Sequence[XNYSSession]) -> list[dict[str, str]]:
    """Build the accidental daily-rotation negative-control schedule."""

    if len(sessions) < 2:
        raise ParityContractError("daily schedule requires two sessions")
    return [
        {
            "signal_session": signal.session_date.isoformat(),
            "signal_at_utc": signal.market_close_utc.isoformat().replace("+00:00", "Z"),
            "entry_session": entry.session_date.isoformat(),
            "entry_at_utc": entry.market_open_utc.isoformat().replace("+00:00", "Z"),
        }
        for signal, entry in zip(sessions, sessions[1:])
    ]


def adverse_fill_price(reference_price: float, *, side: str, cost_bps: float) -> float:
    """Apply all-in adverse fee/slippage at each fill, never favorable costs."""

    if not math.isfinite(reference_price) or reference_price <= 0:
        raise ParityContractError("reference price must be positive and finite")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ParityContractError("cost_bps must be finite and non-negative")
    if side == "buy":
        return reference_price * (1.0 + cost_bps / 10_000.0)
    if side == "sell":
        return reference_price * (1.0 - cost_bps / 10_000.0)
    raise ParityContractError("side must be buy or sell")


def _validate_bars(bars: Sequence[DailyBar]) -> None:
    if not bars:
        raise ParityContractError("daily bars are missing")
    dates = [bar.session_date for bar in bars]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ParityContractError("daily bars must be unique and ordered")
    for bar in bars:
        values = (bar.open, bar.high, bar.low, bar.close)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ParityContractError("OHLC must be positive and finite")
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.low > bar.high:
            raise ParityContractError("OHLC geometry is invalid")


def simulate_position(
    bars: Sequence[DailyBar],
    *,
    atr_at_signal: float,
    cost_bps_per_side: float,
    contract: SharedExitContract = SharedExitContract(),
) -> dict[str, object]:
    """Execute one causal long position under the frozen shared exit contract.

    Stops derived from a completed bar become active on the next session.  This
    avoids pretending that an OHLC bar reveals whether its high occurred before
    its low.  Opening gaps are evaluated before the intraday high/low path, and
    a bar touching both the active stop and target exits at the stop.
    """

    _validate_bars(bars)
    if not math.isfinite(atr_at_signal) or atr_at_signal <= 0:
        raise ParityContractError("atr_at_signal must be positive and finite")
    if contract.same_bar_stop_and_target != "stop_first":
        raise ParityContractError("only conservative stop_first ordering is allowed")
    if contract.stop_update_timing != "completed_bar_for_next_session":
        raise ParityContractError("stop updates must be causal and next-session effective")

    entry_reference = bars[0].open
    entry_fill = adverse_fill_price(entry_reference, side="buy", cost_bps=cost_bps_per_side)
    initial_risk = contract.initial_stop_atr * atr_at_signal
    active_stop = entry_fill - initial_risk
    target = entry_fill + contract.profit_target_atr * atr_at_signal
    peak = entry_fill
    marks: list[dict[str, object]] = []
    exit_reference: float | None = None
    exit_reason = ""
    exit_session: date | None = None

    for held, bar in enumerate(bars, start=1):
        if held > 1:
            if bar.open <= active_stop:
                exit_reference, exit_reason = bar.open, "stop_gap_open"
            elif bar.open >= target:
                exit_reference, exit_reason = target, "target_frozen_no_gap_credit"
        if exit_reference is None and bar.low <= active_stop:
            exit_reference, exit_reason = active_stop, "stop_first"
        elif exit_reference is None and bar.high >= target:
            exit_reference, exit_reason = target, "target"

        if exit_reference is not None:
            exit_session = bar.session_date
            exit_fill = adverse_fill_price(exit_reference, side="sell", cost_bps=cost_bps_per_side)
            marks.append(
                {
                    "session": bar.session_date.isoformat(),
                    "state": "closed",
                    "mark_price": exit_fill,
                    "active_stop": active_stop,
                }
            )
            break

        peak = max(peak, bar.high)
        next_stop = active_stop
        if peak - entry_fill >= contract.break_even_trigger_r * initial_risk:
            next_stop = max(next_stop, entry_fill, peak - contract.trail_atr * atr_at_signal)
        marks.append(
            {
                "session": bar.session_date.isoformat(),
                "state": "open",
                "mark_price": bar.close,
                "active_stop": active_stop,
                "next_session_stop": next_stop,
            }
        )
        active_stop = next_stop
        if held >= contract.max_hold_sessions:
            exit_session = bar.session_date
            exit_reference = bar.close
            exit_reason = "max_hold_close"
            exit_fill = adverse_fill_price(exit_reference, side="sell", cost_bps=cost_bps_per_side)
            marks[-1].update({"state": "closed", "mark_price": exit_fill})
            break
    else:
        exit_fill = None

    return {
        "contract": asdict(contract),
        "entry_session": bars[0].session_date.isoformat(),
        "entry_reference": entry_reference,
        "entry_fill": entry_fill,
        "initial_stop": entry_fill - initial_risk,
        "target": target,
        "exit_session": exit_session.isoformat() if exit_session else None,
        "exit_reference": exit_reference,
        "exit_fill": exit_fill,
        "exit_reason": exit_reason or None,
        "daily_marks": marks,
    }


def daily_portfolio_mark_to_market(
    *,
    settled_cash: float,
    open_positions: Iterable[Mapping[str, float]],
) -> float:
    """Mark a portfolio at each completed session close without forward prices."""

    if not math.isfinite(settled_cash):
        raise ParityContractError("settled_cash must be finite")
    equity = settled_cash
    for row in open_positions:
        try:
            qty = float(row["qty"])
            close = float(row["close"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ParityContractError("position mark requires qty and close") from exc
        if not math.isfinite(qty) or qty < 0 or not math.isfinite(close) or close <= 0:
            raise ParityContractError("position mark values are invalid")
        equity += qty * close
    if not math.isfinite(equity) or equity < 0:
        raise ParityContractError("daily equity is invalid")
    return equity


def intramonth_portfolio_stop_triggered(
    *, month_start_equity: float, current_equity: float, threshold_pct: float = 0.08
) -> bool:
    if not all(math.isfinite(value) and value > 0 for value in (month_start_equity, current_equity)):
        raise ParityContractError("equity values must be positive and finite")
    if not math.isfinite(threshold_pct) or not 0 < threshold_pct < 1:
        raise ParityContractError("portfolio stop threshold must be between zero and one")
    return current_equity / month_start_equity - 1.0 <= -threshold_pct


def daily_max_drawdown(initial_equity: float, daily_equity: Sequence[float]) -> float:
    """Return negative fractional DD and include initial capital in the peak."""

    if not math.isfinite(initial_equity) or initial_equity <= 0:
        raise ParityContractError("initial equity must be positive")
    peak = initial_equity
    max_drawdown = 0.0
    for value in daily_equity:
        if not math.isfinite(value) or value < 0:
            raise ParityContractError("daily equity must be finite and non-negative")
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0)
    return max_drawdown
