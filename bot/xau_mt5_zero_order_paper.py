"""Pure, zero-order paper accounting for the XAU research lane.

This module intentionally contains no broker, network, credential, or execution
surface.  It accepts already-observed public quotes and produces immutable
research records only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
CONTROL_JOURNAL_UTC_HOUR = 6


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _finite(value: float | None, name: str) -> float:
    if value is None or not math.isfinite(float(value)):
        raise ValueError(f"{name} missing or non-finite")
    return float(value)


def _positive(value: float | None, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _side(value: str) -> str:
    value = str(value).lower()
    if value not in {"long", "short"}:
        raise ValueError("side must be long or short")
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True)
class CostContract:
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    commission_per_unit: float = 0.0
    point_value: float = 1.0

    def __post_init__(self) -> None:
        for name in ("spread_bps", "slippage_bps", "commission_per_unit"):
            value = _finite(getattr(self, name), name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if _finite(self.point_value, "point_value") <= 0:
            raise ValueError("point_value must be positive")
        if self.slippage_bps + self.spread_bps / 2.0 >= 10_000:
            raise ValueError("combined price stress must remain below 10000 bps")


@dataclass(frozen=True)
class SignalEvent:
    signal_id: str
    strategy: str
    strategy_version: str
    symbol: str
    side: str
    event_at: datetime
    source_candle_end: datetime
    data_source_hash: str
    entry: float
    stop: float
    take_profit: float
    validity_until: datetime
    regime: str
    feature_snapshot_hash: str
    prereg_hash: str
    evidence_universe_role: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_at", _utc(self.event_at))
        object.__setattr__(self, "source_candle_end", _utc(self.source_candle_end))
        object.__setattr__(self, "validity_until", _utc(self.validity_until))
        object.__setattr__(self, "side", _side(self.side))
        if self.source_candle_end > self.event_at:
            raise ValueError("source candle cannot end after signal event")
        if self.validity_until <= self.event_at:
            raise ValueError("signal validity window must be positive")
        entry = _positive(self.entry, "entry")
        stop = _positive(self.stop, "stop")
        target = _positive(self.take_profit, "take_profit")
        if self.side == "long" and not stop < entry < target:
            raise ValueError("long geometry must satisfy stop < entry < take_profit")
        if self.side == "short" and not target < entry < stop:
            raise ValueError("short geometry must satisfy take_profit < entry < stop")
        for name in ("signal_id", "strategy", "strategy_version", "symbol", "data_source_hash", "regime", "feature_snapshot_hash", "prereg_hash", "evidence_universe_role"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")


@dataclass(frozen=True)
class QuoteSnapshot:
    observed_at: datetime
    bid: float | None
    ask: float | None
    source_hash: str
    freshness_age_seconds: float
    session: str | None = None
    quote_valid: bool = True
    low: float | None = None
    high: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        age = _finite(self.freshness_age_seconds, "freshness_age_seconds")
        if age < 0:
            raise ValueError("freshness_age_seconds must be non-negative")
        bid = _positive(self.bid, "bid") if self.bid is not None else None
        ask = _positive(self.ask, "ask") if self.ask is not None else None
        if bid is not None and ask is not None:
            if bid > ask:
                raise ValueError("crossed quote")
        if self.low is not None:
            _positive(self.low, "low")
        if self.high is not None:
            _positive(self.high, "high")
        if (
            self.low is not None
            and self.high is not None
            and float(self.low) > float(self.high)
        ):
            raise ValueError("quote range is crossed")
        if not str(self.source_hash).strip():
            raise ValueError("source_hash is required")


def validate_quote(
    quote: QuoteSnapshot,
    *,
    observed_at: datetime | None = None,
    max_age_seconds: float = 60.0,
    allowed_sessions: set[str] | None = None,
) -> tuple[bool, str]:
    if not quote.quote_valid:
        return False, "quote_marked_invalid"
    if quote.bid is None or quote.ask is None:
        return False, "missing_bid_ask"
    if quote.bid > quote.ask:
        return False, "crossed_bid_ask"
    if quote.freshness_age_seconds > max_age_seconds:
        return False, "stale_quote"
    if allowed_sessions is not None and quote.session not in allowed_sessions:
        return False, "out_of_session"
    if observed_at is not None and quote.observed_at > _utc(observed_at):
        return False, "future_quote"
    return True, "ok"


@dataclass(frozen=True)
class PaperPosition:
    position_id: str
    signal_id: str
    decision_id: str
    symbol: str
    side: str
    quantity: float
    entry_at: datetime
    entry_reference_price: float
    entry_fill: float
    stop: float
    take_profit: float
    point_value: float
    state: str = "open"
    last_valuation_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_at", _utc(self.entry_at))
        if self.last_valuation_at is not None:
            object.__setattr__(self, "last_valuation_at", _utc(self.last_valuation_at))
        object.__setattr__(self, "side", _side(self.side))
        if _finite(self.quantity, "quantity") <= 0:
            raise ValueError("quantity must be positive")
        if self.state not in {"pending", "open", "closed", "invalid", "expired"}:
            raise ValueError("invalid position state")
        entry_reference = _positive(self.entry_reference_price, "entry_reference_price")
        entry_fill = _positive(self.entry_fill, "entry_fill")
        stop = _positive(self.stop, "stop")
        target = _positive(self.take_profit, "take_profit")
        _positive(self.point_value, "point_value")
        for name in ("position_id", "signal_id", "decision_id", "symbol"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"{name} is required")
        if self.side == "long" and not stop < entry_fill < target:
            raise ValueError("long position geometry is invalid")
        if self.side == "short" and not target < entry_fill < stop:
            raise ValueError("short position geometry is invalid")
        if entry_reference <= 0:
            raise ValueError("entry_reference_price must be positive")


def _entry_reference(side: str, quote: QuoteSnapshot) -> float:
    return float(quote.ask if side == "long" else quote.bid)


def _exit_reference(side: str, quote: QuoteSnapshot) -> float:
    return float(quote.bid if side == "long" else quote.ask)


def _slipped(price: float, side: str, *, entering: bool, costs: CostContract) -> float:
    # The quote already carries the observed bid/ask. ``spread_bps`` is an
    # explicit additional stress, split equally across entry and exit.
    rate = (costs.slippage_bps + costs.spread_bps / 2.0) / 10_000.0
    adverse = side == "long" if entering else side == "short"
    return price * (1 + rate) if adverse else price * (1 - rate)


def open_position(
    signal: SignalEvent,
    quote: QuoteSnapshot,
    *,
    quantity: float,
    costs: CostContract | None = None,
    decision_id: str | None = None,
    max_age_seconds: float = 60.0,
    allowed_sessions: set[str] | None = None,
) -> PaperPosition:
    costs = costs or CostContract()
    ok, reason = validate_quote(
        quote,
        max_age_seconds=max_age_seconds,
        allowed_sessions=allowed_sessions,
    )
    if not ok:
        raise ValueError(f"invalid quote: {reason}")
    if quote.observed_at < signal.event_at:
        raise ValueError("quote precedes signal")
    if quote.observed_at > signal.validity_until:
        raise ValueError("quote is outside signal validity window")
    q = _finite(quantity, "quantity")
    if q <= 0:
        raise ValueError("quantity must be positive")
    reference = _entry_reference(signal.side, quote)
    fill = _slipped(reference, signal.side, entering=True, costs=costs)
    position_id = _hash({"signal_id": signal.signal_id, "decision_id": decision_id or signal.signal_id, "entry_at": quote.observed_at.isoformat()})[:24]
    return PaperPosition(
        position_id=position_id,
        signal_id=signal.signal_id,
        decision_id=decision_id or signal.signal_id,
        symbol=signal.symbol,
        side=signal.side,
        quantity=q,
        entry_at=quote.observed_at,
        entry_reference_price=reference,
        entry_fill=fill,
        stop=signal.stop,
        take_profit=signal.take_profit,
        point_value=costs.point_value,
    )


@dataclass(frozen=True)
class PaperOutcome:
    position_id: str
    signal_id: str
    symbol: str
    side: str
    exit_at: datetime
    exit_reference_price: float | None
    exit_fill: float | None
    close_reason: str
    gross_pnl: float
    net_pnl: float
    r_multiple: float
    mae_r: float
    mfe_r: float
    holding_seconds: float
    gap_amount: float
    quote_freshness_age_seconds: float
    data_quality: str
    source_hash: str
    stop_first_tie: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "exit_at", _utc(self.exit_at))
        object.__setattr__(self, "side", _side(self.side))
        if self.close_reason not in {"stop", "take_profit", "time_exit", "gap", "invalid_data"}:
            raise ValueError("invalid close_reason")


def evaluate_position(
    position: PaperPosition,
    quote: QuoteSnapshot,
    *,
    costs: CostContract | None = None,
    previous_exit_reference: float | None = None,
    time_exit: bool = False,
    max_age_seconds: float = 60.0,
    allowed_sessions: set[str] | None = None,
) -> PaperOutcome:
    costs = costs or CostContract(point_value=position.point_value)
    if not math.isclose(
        costs.point_value,
        position.point_value,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("cost contract point_value differs from position")
    if position.state != "open":
        raise ValueError("evaluation requires an open position")
    if quote.observed_at < position.entry_at:
        return PaperOutcome(
            position.position_id,
            position.signal_id,
            position.symbol,
            position.side,
            quote.observed_at,
            None,
            None,
            "invalid_data",
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            quote.freshness_age_seconds,
            "quote_precedes_position",
            quote.source_hash,
        )
    ok, reason = validate_quote(quote, max_age_seconds=max_age_seconds, allowed_sessions=allowed_sessions)
    if not ok:
        return PaperOutcome(position.position_id, position.signal_id, position.symbol, position.side, quote.observed_at, None, None, "invalid_data", 0.0, 0.0, 0.0, 0.0, 0.0, max(0.0, (quote.observed_at - position.entry_at).total_seconds()), 0.0, quote.freshness_age_seconds, reason, quote.source_hash)

    reference = _exit_reference(position.side, quote)
    low = float(quote.low if quote.low is not None else reference)
    high = float(quote.high if quote.high is not None else reference)
    if position.side == "long":
        stop_touched = low <= position.stop
        target_touched = high >= position.take_profit
        gap = reference < position.stop and (
            previous_exit_reference is None or previous_exit_reference > position.stop
        )
        adverse = position.entry_reference_price - low
        favorable = high - position.entry_reference_price
    else:
        stop_touched = high >= position.stop
        target_touched = low <= position.take_profit
        gap = reference > position.stop and (
            previous_exit_reference is None or previous_exit_reference < position.stop
        )
        adverse = high - position.entry_reference_price
        favorable = position.entry_reference_price - low

    tie = stop_touched and target_touched
    if gap:
        reason_out, trigger = "gap", reference
    elif stop_touched:
        reason_out, trigger = "stop", position.stop
    elif target_touched:
        reason_out, trigger = "take_profit", position.take_profit
    elif time_exit:
        reason_out, trigger = "time_exit", reference
    else:
        raise ValueError("quote does not close position")

    exit_fill = _slipped(trigger, position.side, entering=False, costs=costs)
    direction = 1.0 if position.side == "long" else -1.0
    gross = position.quantity * (exit_fill - position.entry_fill) * direction * position.point_value
    net = gross - 2 * position.quantity * costs.commission_per_unit
    risk = position.quantity * abs(position.entry_fill - position.stop) * position.point_value
    r = net / risk if risk else 0.0
    risk_unit = abs(position.entry_reference_price - position.stop)
    mae_r = max(0.0, adverse) / risk_unit if risk_unit else 0.0
    mfe_r = max(0.0, favorable) / risk_unit if risk_unit else 0.0
    gap_amount = abs(position.stop - reference) if reason_out == "gap" else 0.0
    return PaperOutcome(position.position_id, position.signal_id, position.symbol, position.side, quote.observed_at, reference, exit_fill, reason_out, gross, net, r, mae_r, mfe_r, max(0.0, (quote.observed_at - position.entry_at).total_seconds()), gap_amount, quote.freshness_age_seconds, "ok", quote.source_hash, tie)


@dataclass(frozen=True)
class ControlAssignment:
    assignment_id: str
    decision_id: str
    symbol: str
    control_side: str
    control_entry_at: datetime
    strategy_event_at: datetime
    prereg_hash: str
    seed: str
    commit_hash: str
    state: str
    collision_index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_entry_at", _utc(self.control_entry_at))
        object.__setattr__(self, "strategy_event_at", _utc(self.strategy_event_at))
        object.__setattr__(self, "control_side", _side(self.control_side))
        if self.state not in {"ready", "pending"}:
            raise ValueError("control state must be ready or pending")
        if self.collision_index < 0:
            raise ValueError("collision_index must be non-negative")


def _hour_candidates(start: datetime, end: datetime) -> list[datetime]:
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValueError("window must end after start")
    cursor = start.replace(minute=0, second=0, microsecond=0)
    result: list[datetime] = []
    while cursor <= end:
        if start <= cursor <= end:
            result.append(cursor)
        cursor += timedelta(hours=1)
    return result


def assign_control(
    *,
    decision_id: str,
    symbol: str,
    strategy_side: str,
    event_at: datetime,
    window_start: datetime,
    window_end: datetime,
    prereg_hash: str,
    now: datetime | None = None,
    collision_index: int = 0,
    occupied_entries: Sequence[datetime] = (),
) -> ControlAssignment:
    event_at, now = _utc(event_at), _utc(now or event_at)
    strategy_side = _side(strategy_side)
    occupied = {_utc(value) for value in occupied_entries}
    candidates = [candidate for candidate in _hour_candidates(window_start, window_end) if candidate != event_at.replace(minute=0, second=0, microsecond=0) and candidate not in occupied]
    if not candidates:
        raise ValueError("window has no control candidates")
    seed = _hash({"decision_id": decision_id, "symbol": symbol, "event_at": event_at.isoformat(), "prereg_hash": prereg_hash, "collision_index": collision_index})
    index = int(seed[:16], 16) % len(candidates)
    control_entry_at = candidates[index]
    control_side = "short" if int(seed[16:18], 16) % 2 else "long"
    assignment_id = _hash({"seed": seed, "entry": control_entry_at.isoformat(), "side": control_side})[:24]
    payload = {"assignment_id": assignment_id, "decision_id": decision_id, "symbol": symbol, "control_side": control_side, "control_entry_at": control_entry_at.isoformat(), "prereg_hash": prereg_hash, "seed": seed, "collision_index": collision_index}
    return ControlAssignment(assignment_id, decision_id, symbol, control_side, control_entry_at, event_at, prereg_hash, seed, _hash(payload), "pending" if control_entry_at > now else "ready", collision_index)


class JournalCorruption(RuntimeError):
    pass


class HashChainJournal:
    """Append-only JSONL journal with deterministic idempotency keys."""

    def __init__(self, path: str | Path, *, stream: str = "xau_control_0600") -> None:
        self.path = Path(path)
        self.stream = stream

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line_number, raw in enumerate(self.path.read_text().splitlines(), 1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise JournalCorruption(f"invalid JSON at line {line_number}") from exc
            if not isinstance(row, dict) or "row_hash" not in row:
                raise JournalCorruption(f"invalid row at line {line_number}")
            if row.get("stream") != self.stream:
                raise JournalCorruption(f"stream mismatch at line {line_number}")
            expected = row["row_hash"]
            body = {key: value for key, value in row.items() if key != "row_hash"}
            if _hash(body) != expected:
                raise JournalCorruption(f"row hash mismatch at line {line_number}")
            parent = rows[-1]["row_hash"] if rows else "GENESIS"
            if row.get("parent_hash") != parent:
                raise JournalCorruption(f"parent hash mismatch at line {line_number}")
            rows.append(row)
        return rows

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def append(self, payload: Mapping[str, Any], *, idempotency_key: str, prereg_hash: str, source_hash: str) -> dict[str, Any]:
        with self._locked():
            rows = self._rows()
            for row in rows:
                if row.get("idempotency_key") == idempotency_key:
                    if (
                        row.get("payload") != dict(payload)
                        or row.get("prereg_hash") != prereg_hash
                        or row.get("source_hash") != source_hash
                    ):
                        raise JournalCorruption(
                            "idempotency key reused with different payload"
                        )
                    return row
            body = {
                "event_id": _hash(
                    {"stream": self.stream, "idempotency_key": idempotency_key}
                )[:32],
                "parent_hash": rows[-1]["row_hash"] if rows else "GENESIS",
                "prereg_hash": prereg_hash,
                "source_hash": source_hash,
                "created_at_utc": datetime.now(UTC).isoformat(),
                "idempotency_key": idempotency_key,
                "stream": self.stream,
                "payload": dict(payload),
            }
            row = {**body, "row_hash": _hash(body)}
            file_fd = os.open(
                self.path,
                os.O_CREAT | os.O_APPEND | os.O_WRONLY,
                0o600,
            )
            try:
                os.chmod(self.path, 0o600)
                with os.fdopen(file_fd, "a", encoding="utf-8") as handle:
                    file_fd = -1
                    handle.write(
                        json.dumps(row, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                if file_fd >= 0:
                    os.close(file_fd)
            return row

    def validate(self) -> int:
        with self._locked():
            return len(self._rows())


__all__ = [
    "CONTROL_JOURNAL_UTC_HOUR", "ControlAssignment", "CostContract", "HashChainJournal", "JournalCorruption", "PaperOutcome", "PaperPosition", "QuoteSnapshot", "SignalEvent", "assign_control", "evaluate_position", "open_position", "validate_quote",
]
