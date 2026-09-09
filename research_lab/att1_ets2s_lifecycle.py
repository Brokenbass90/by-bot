"""Synthetic, immutable ATT1/ETS2S exposure replay with no broker capability.

``terminal_eligible`` is only exposure finality for this reducer.  It is not
clean-cohort, protection-lifecycle, L3 accounting, parity, or promotion proof.
Decimal text is deliberately bounded to 128 characters, 64 coefficient digits,
and an absolute exponent of 64 so replay rejects hostile inputs instead of
rounding or consuming unbounded resources.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Mapping


MONEY_AUTHORITY = False
ORDERS_ALLOWED = False
PRIVATE_API_ALLOWED = False
PROMOTION_AUTHORITY = False
MAX_DECIMAL_TEXT_LENGTH = 128
MAX_DECIMAL_DIGITS = 64
MAX_DECIMAL_EXPONENT_ABS = 64


class LifecycleViolation(ValueError):
    """Raised when a synthetic receipt cannot be safely replayed."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise LifecycleViolation(f"{field} must be a nonempty string")
    return value


def _decimal_text(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    if (
        isinstance(value, bool)
        or not isinstance(value, str)
        or not value
        or len(value) > MAX_DECIMAL_TEXT_LENGTH
        or value.strip() != value
    ):
        raise LifecycleViolation(f"{field} must be a bounded finite decimal string")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise LifecycleViolation(f"{field} must be a bounded finite decimal string") from exc
    decimal_tuple = decimal.as_tuple()
    if (
        not decimal.is_finite()
        or len(decimal_tuple.digits) > MAX_DECIMAL_DIGITS
        or abs(decimal_tuple.exponent) > MAX_DECIMAL_EXPONENT_ABS
        or decimal < 0
        or (not allow_zero and decimal == 0)
    ):
        raise LifecycleViolation(f"{field} must be a bounded finite positive decimal string")
    return decimal


def _positive_decimal(value: object, field: str) -> Decimal:
    return _decimal_text(value, field)


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LifecycleViolation(f"{field} must be a nonnegative integer")
    return value


def _coefficient(decimal: Decimal) -> int:
    return int("".join(str(digit) for digit in decimal.as_tuple().digits))


def _steps(value: object, step: Decimal, field: str, *, allow_zero: bool = False) -> int:
    quantity = _decimal_text(value, field, allow_zero=allow_zero)
    quantity_coefficient = _coefficient(quantity)
    step_coefficient = _coefficient(step)
    exponent_gap = quantity.as_tuple().exponent - step.as_tuple().exponent
    if exponent_gap >= 0:
        numerator = quantity_coefficient * (10**exponent_gap)
        denominator = step_coefficient
    else:
        numerator = quantity_coefficient
        denominator = step_coefficient * (10 ** (-exponent_gap))
    if numerator % denominator:
        raise LifecycleViolation(f"{field} must be an exact quantity step multiple")
    return numerator // denominator


def _quantity(step: Decimal, steps: int) -> Decimal:
    coefficient = _coefficient(step) * steps
    exponent = step.as_tuple().exponent
    digits = tuple(int(digit) for digit in str(coefficient))
    return Decimal((0, digits, exponent))


def _digest(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExposurePlan:
    book: str
    sleeve: str
    symbol: str
    decision_id: str
    order_id: str
    profile_id: str
    qty_step: str
    requested_qty: str
    submit_ms: int

    def __post_init__(self) -> None:
        for field in ("book", "sleeve", "symbol", "decision_id", "order_id", "profile_id"):
            _text(getattr(self, field), field)
        if not self.profile_id.startswith("SYNTHETIC_") and self.profile_id != 'BROKER_REPLAY_ATT1_V1':
            raise LifecycleViolation("profile_id must be synthetic or explicit broker replay")
        step = _positive_decimal(self.qty_step, "qty_step")
        _steps(self.requested_qty, step, "requested_qty")
        _nonnegative_int(self.submit_ms, "submit_ms")


@dataclass(frozen=True)
class ExposureEvent:
    event_id: str
    kind: str
    order_id: str
    exchange_ms: int
    received_ms: int
    execution_id: str | None = None
    qty: str | None = None


@dataclass(frozen=True)
class ExposureState:
    plan: ExposurePlan
    qty_step: Decimal
    requested_steps: int
    held_steps: int
    pending_entry_steps: int
    protected_steps: int | None
    entry_filled_steps: int
    exit_filled_steps: int
    protection_intended: bool
    cancel_requested: bool
    entry_final: bool
    incidents: frozenset[str]
    last_exchange_ms: int | None
    last_received_ms: int | None
    accepted_events: tuple[ExposureEvent, ...]
    accepted_event_fingerprints: Mapping[str, str]
    execution_fingerprints: Mapping[str, str]

    def _quantity(self, steps: int) -> Decimal:
        return _quantity(self.qty_step, steps)

    @property
    def held_qty(self) -> Decimal:
        return self._quantity(self.held_steps)

    @property
    def pending_entry_qty(self) -> Decimal:
        return self._quantity(self.pending_entry_steps)

    @property
    def protected_qty(self) -> Decimal:
        return self._quantity(self.protected_steps or 0)

    @property
    def unprotected_qty(self) -> Decimal:
        return self._quantity(self.held_steps - (self.protected_steps or 0))

    @property
    def entry_filled_qty(self) -> Decimal:
        return self._quantity(self.entry_filled_steps)

    @property
    def exit_filled_qty(self) -> Decimal:
        return self._quantity(self.exit_filled_steps)

    @property
    def terminal_eligible(self) -> bool:
        return self.entry_final and self.held_steps == 0 and not self.incidents


def initial_state(plan: ExposurePlan) -> ExposureState:
    if not isinstance(plan, ExposurePlan):
        raise LifecycleViolation("plan must be an ExposurePlan")
    step = _positive_decimal(plan.qty_step, "qty_step")
    requested_steps = _steps(plan.requested_qty, step, "requested_qty")
    return ExposureState(
        plan=plan,
        qty_step=step,
        requested_steps=requested_steps,
        held_steps=0,
        pending_entry_steps=requested_steps,
        protected_steps=None,
        entry_filled_steps=0,
        exit_filled_steps=0,
        protection_intended=False,
        cancel_requested=False,
        entry_final=False,
        incidents=frozenset(),
        last_exchange_ms=None,
        last_received_ms=None,
        accepted_events=(),
        accepted_event_fingerprints=MappingProxyType({}),
        execution_fingerprints=MappingProxyType({}),
    )


_FILL_KINDS = frozenset({"ENTRY_FILL", "EXIT_FILL"})
_QTY_KINDS = frozenset({"ENTRY_FILL", "EXIT_FILL", "PROTECTION_ACK"})
_KINDS = frozenset({"ENTRY_ACK", "ENTRY_FILL", "CANCEL_REQUEST", "ENTRY_FINAL", "EXIT_FILL", "PROTECTION_ACK", "UNKNOWN_PROTECTION"})


def _event_payload(event: ExposureEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "kind": event.kind,
        "order_id": event.order_id,
        "exchange_ms": event.exchange_ms,
        "received_ms": event.received_ms,
        "execution_id": event.execution_id,
        "qty": event.qty,
    }


def _execution_payload(event: ExposureEvent) -> dict[str, object]:
    payload = _event_payload(event)
    del payload["event_id"]
    return payload


def _validate_event(state: ExposureState, event: ExposureEvent) -> tuple[str, int | None]:
    if not isinstance(event, ExposureEvent):
        raise LifecycleViolation("event must be an ExposureEvent")
    _text(event.event_id, "event_id")
    if _text(event.kind, "kind") not in _KINDS:
        raise LifecycleViolation("unknown event kind")
    if event.order_id != state.plan.order_id:
        raise LifecycleViolation("foreign order_id")
    exchange_ms = _nonnegative_int(event.exchange_ms, "exchange_ms")
    received_ms = _nonnegative_int(event.received_ms, "received_ms")
    if not (state.plan.submit_ms <= exchange_ms <= received_ms):
        raise LifecycleViolation("timestamps must satisfy submit<=exchange<=received")
    if event.kind in _QTY_KINDS:
        if event.qty is None:
            raise LifecycleViolation(f"{event.kind} requires qty")
        qty_steps = _steps(event.qty, state.qty_step, "qty")
    elif event.qty is not None:
        raise LifecycleViolation(f"{event.kind} cannot carry qty")
    else:
        qty_steps = None
    if event.kind in _FILL_KINDS:
        _text(event.execution_id, "execution_id")
    elif event.execution_id is not None:
        raise LifecycleViolation(f"{event.kind} cannot carry execution_id")
    return _digest(_event_payload(event)), qty_steps


def _validate_monotonic(state: ExposureState, event: ExposureEvent) -> None:
    if state.last_exchange_ms is not None and event.exchange_ms < state.last_exchange_ms:
        raise LifecycleViolation("decreasing exchange timestamps are unresolved")
    if state.last_received_ms is not None and event.received_ms < state.last_received_ms:
        raise LifecycleViolation("received timestamps must be nondecreasing")


def _with_event(
    state: ExposureState,
    event: ExposureEvent,
    event_fingerprint: str,
    execution_fingerprint: str | None = None,
    *,
    advance_watermarks: bool = True,
) -> ExposureState:
    events = dict(state.accepted_event_fingerprints)
    events[event.event_id] = event_fingerprint
    executions = dict(state.execution_fingerprints)
    if execution_fingerprint is not None:
        executions[event.execution_id] = execution_fingerprint
    return replace(
        state,
        last_exchange_ms=event.exchange_ms if advance_watermarks else state.last_exchange_ms,
        last_received_ms=event.received_ms if advance_watermarks else state.last_received_ms,
        accepted_events=state.accepted_events + (event,),
        accepted_event_fingerprints=MappingProxyType(events),
        execution_fingerprints=MappingProxyType(executions),
    )


def apply_event(state: ExposureState, event: ExposureEvent) -> ExposureState:
    if not isinstance(state, ExposureState):
        raise LifecycleViolation("state must be an ExposureState")
    if not isinstance(event, ExposureEvent):
        raise LifecycleViolation("event must be an ExposureEvent")
    event_fingerprint, qty_steps = _validate_event(state, event)
    previous_event = state.accepted_event_fingerprints.get(event.event_id)
    if previous_event is not None:
        if previous_event == event_fingerprint:
            return state
        raise LifecycleViolation("conflicting event_id reuse")

    execution_fingerprint = None
    if event.kind in _FILL_KINDS:
        execution_fingerprint = _digest(_execution_payload(event))
        previous_execution = state.execution_fingerprints.get(event.execution_id)
        if previous_execution is not None:
            if previous_execution != execution_fingerprint:
                raise LifecycleViolation("conflicting execution_id reuse")
            return _with_event(state, event, event_fingerprint, advance_watermarks=False)
    _validate_monotonic(state, event)

    next_state = state
    if event.kind == "ENTRY_FILL":
        unexpected = next_state.entry_final or qty_steps > next_state.pending_entry_steps
        if unexpected:
            next_state = replace(next_state, incidents=next_state.incidents | {"INCIDENT_UNEXPECTED_ENTRY_FILL"})
        next_state = replace(
            next_state,
            held_steps=next_state.held_steps + qty_steps,
            pending_entry_steps=max(0, next_state.pending_entry_steps - qty_steps),
            entry_filled_steps=next_state.entry_filled_steps + qty_steps,
            protection_intended=True,
        )
    elif event.kind == "EXIT_FILL":
        if qty_steps > next_state.held_steps:
            raise LifecycleViolation("exit qty exceeds held qty")
        held_steps = next_state.held_steps - qty_steps
        protected_steps = None if next_state.protected_steps is None else min(next_state.protected_steps, held_steps)
        next_state = replace(
            next_state,
            held_steps=held_steps,
            protected_steps=protected_steps,
            exit_filled_steps=next_state.exit_filled_steps + qty_steps,
        )
    elif event.kind == "CANCEL_REQUEST":
        next_state = replace(next_state, cancel_requested=True)
    elif event.kind == "ENTRY_FINAL":
        next_state = replace(next_state, entry_final=True, pending_entry_steps=0)
    elif event.kind == "PROTECTION_ACK":
        if qty_steps > next_state.held_steps:
            raise LifecycleViolation("protected qty exceeds held qty")
        next_state = replace(next_state, protected_steps=qty_steps)
    elif event.kind == "UNKNOWN_PROTECTION":
        next_state = replace(next_state, protected_steps=None)

    return _with_event(next_state, event, event_fingerprint, execution_fingerprint)


def replay(plan: ExposurePlan, events: tuple[ExposureEvent, ...] | list[ExposureEvent]) -> ExposureState:
    state = initial_state(plan)
    for event in events:
        state = apply_event(state, event)
    return state


def target_close_qty(initial_qty: object, remaining_qty: object, qty_step: object, fraction: object, final: bool = False) -> Decimal:
    step = _positive_decimal(qty_step, "qty_step")
    initial_steps = _steps(initial_qty, step, "initial_qty")
    remaining_steps = _steps(remaining_qty, step, "remaining_qty", allow_zero=True)
    if remaining_steps > initial_steps:
        raise LifecycleViolation("remaining_qty cannot exceed initial_qty")
    fraction_decimal = _positive_decimal(fraction, "fraction")
    if fraction_decimal > 1:
        raise LifecycleViolation("fraction must be in (0, 1]")
    if not isinstance(final, bool):
        raise LifecycleViolation("final must be bool")
    if final:
        return _quantity(step, remaining_steps)
    fraction_coefficient = _coefficient(fraction_decimal)
    fraction_exponent = fraction_decimal.as_tuple().exponent
    product = initial_steps * fraction_coefficient
    target_steps = product * (10**fraction_exponent) if fraction_exponent >= 0 else product // (10 ** (-fraction_exponent))
    return _quantity(step, min(target_steps, remaining_steps))
