"""Pure synthetic short-linear-USDT accounting; it has no money authority."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re


MONEY_AUTHORITY = False
ORDERS_ALLOWED = False
PRIVATE_API_ALLOWED = False
PROMOTION_AUTHORITY = False

MAX_DECIMAL_TEXT_LENGTH = 128
MAX_DECIMAL_DIGITS = 64
MAX_DECIMAL_EXPONENT_ABS = 64
_DECIMAL = re.compile(r"[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")
_SHA256 = re.compile(r"[0-9a-f]{64}$")


class AccountingViolation(ValueError):
    """Raised when a synthetic ledger receipt is not safe to replay."""


@dataclass(frozen=True)
class AccountingPlan:
    profile_id: str
    accepted_stop: str
    planned_risk_amount: str
    currency: str
    source_sha256: str


@dataclass(frozen=True)
class Execution:
    event_id: str
    execution_id: str
    kind: str
    qty: str
    price: str
    fee_amount: str | None
    fee_currency: str
    fee_source_sha256: str
    liquidity: str
    exchange_ms: int
    received_ms: int
    source_sha256: str


@dataclass(frozen=True)
class EntryFinal:
    event_id: str
    exchange_ms: int
    received_ms: int
    source_sha256: str


@dataclass(frozen=True)
class FundingSettlement:
    event_id: str
    settlement_id: str
    settlement_ms: int
    exchange_ms: int
    received_ms: int
    qty_at_settlement: str
    mark_price: str
    rate: str
    source_sha256: str


@dataclass(frozen=True)
class FundingSchedule:
    settlement_ms: tuple[int, ...]
    start_ms: int
    end_ms: int
    source_sha256: str
    complete: bool


@dataclass(frozen=True)
class AccountingResult:
    held_qty: Fraction
    remaining_basis: Fraction | None
    aggregate_entry_qty: Fraction
    aggregate_entry_notional: Fraction
    gross_realized: Fraction
    known_fee_total: Fraction
    settled_funding: Fraction
    planned_risk_amount: Fraction
    fixed_r0: Fraction | None
    net_realized: Fraction | None
    unrealized: Fraction | None
    net_equity_change: Fraction | None
    closed_net_r: Fraction | None
    issues: frozenset[str]
    funding_coverage_complete: bool
    costs_complete: bool


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AccountingViolation(f"{field} must be a nonempty string")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AccountingViolation(f"{field} must be a 64-character lowercase SHA-256 hex string")
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AccountingViolation(f"{field} must be a nonnegative integer")
    return value


def _decimal(value: object, field: str, *, positive: bool = False, nonnegative: bool = False) -> Fraction:
    if (
        isinstance(value, bool)
        or not isinstance(value, str)
        or not value
        or len(value) > MAX_DECIMAL_TEXT_LENGTH
        or value.strip() != value
        or not _DECIMAL.fullmatch(value)
    ):
        raise AccountingViolation(f"{field} must be a bounded finite decimal string")
    mantissa, exponent_text = re.split(r"[eE]", value, maxsplit=1) if re.search(r"[eE]", value) else (value, "0")
    signless = mantissa[1:] if mantissa[:1] in "+-" else mantissa
    coefficient_text = signless.replace(".", "")
    fractional_digits = len(signless.partition(".")[2])
    exponent = int(exponent_text) - fractional_digits
    if len(coefficient_text) > MAX_DECIMAL_DIGITS or abs(exponent) > MAX_DECIMAL_EXPONENT_ABS:
        raise AccountingViolation(f"{field} must be a bounded finite decimal string")
    coefficient = int(coefficient_text)
    if mantissa.startswith("-"):
        coefficient = -coefficient
    result = Fraction(coefficient) * (10**exponent if exponent >= 0 else Fraction(1, 10 ** (-exponent)))
    if positive and result <= 0:
        raise AccountingViolation(f"{field} must be positive")
    if nonnegative and result < 0:
        raise AccountingViolation(f"{field} must be nonnegative")
    return result


def _times(exchange_ms: object, received_ms: object) -> tuple[int, int]:
    exchange = _integer(exchange_ms, "exchange_ms")
    received = _integer(received_ms, "received_ms")
    if exchange > received:
        raise AccountingViolation("exchange_ms must be <= received_ms")
    return exchange, received


def _validate_plan(plan: object) -> tuple[Fraction, Fraction]:
    if not isinstance(plan, AccountingPlan):
        raise AccountingViolation("plan must be an AccountingPlan")
    _text(plan.profile_id, "profile_id")
    if not plan.profile_id.startswith("SYNTHETIC_"):
        raise AccountingViolation("profile_id must start with SYNTHETIC_")
    if plan.currency != "USDT":
        raise AccountingViolation("only USDT is supported")
    _sha(plan.source_sha256, "plan.source_sha256")
    return _decimal(plan.accepted_stop, "accepted_stop", positive=True), _decimal(
        plan.planned_risk_amount, "planned_risk_amount", positive=True
    )


def _validate_schedule(schedule: FundingSchedule | None) -> FundingSchedule | None:
    if schedule is None:
        return None
    if not isinstance(schedule, FundingSchedule):
        raise AccountingViolation("funding_schedule must be FundingSchedule or None")
    start = _integer(schedule.start_ms, "funding_schedule.start_ms")
    end = _integer(schedule.end_ms, "funding_schedule.end_ms")
    if start > end or not isinstance(schedule.complete, bool):
        raise AccountingViolation("funding_schedule has invalid coverage")
    _sha(schedule.source_sha256, "funding_schedule.source_sha256")
    times = schedule.settlement_ms
    if not isinstance(times, tuple):
        raise AccountingViolation("funding_schedule.settlement_ms must be a tuple")
    parsed = tuple(_integer(item, "funding_schedule.settlement_ms") for item in times)
    if parsed != tuple(sorted(set(parsed))):
        raise AccountingViolation("funding_schedule settlements must be sorted and unique")
    return schedule


def _execution_values(event: Execution) -> tuple[Fraction, Fraction, Fraction | None, int, int]:
    if not isinstance(event, Execution):
        raise AccountingViolation("event must be Execution, EntryFinal, or FundingSettlement")
    _text(event.event_id, "event_id")
    _text(event.execution_id, "execution_id")
    if event.kind not in {"ENTRY", "EXIT"}:
        raise AccountingViolation("execution kind must be ENTRY or EXIT")
    qty = _decimal(event.qty, "qty", positive=True)
    price = _decimal(event.price, "price", positive=True)
    fee = None if event.fee_amount is None else _decimal(event.fee_amount, "fee_amount")
    if event.fee_currency != "USDT":
        raise AccountingViolation("fee_currency must be USDT")
    _sha(event.fee_source_sha256, "fee_source_sha256")
    if event.liquidity not in {"MAKER", "TAKER"}:
        raise AccountingViolation("liquidity must be MAKER or TAKER")
    exchange, received = _times(event.exchange_ms, event.received_ms)
    _sha(event.source_sha256, "execution.source_sha256")
    return qty, price, fee, exchange, received


def _final_values(event: EntryFinal) -> tuple[int, int]:
    if not isinstance(event, EntryFinal):
        raise AccountingViolation("event must be Execution, EntryFinal, or FundingSettlement")
    _text(event.event_id, "event_id")
    exchange, received = _times(event.exchange_ms, event.received_ms)
    _sha(event.source_sha256, "entry_final.source_sha256")
    return exchange, received


def _funding_values(event: FundingSettlement) -> tuple[Fraction, Fraction, Fraction, int, int]:
    if not isinstance(event, FundingSettlement):
        raise AccountingViolation("event must be Execution, EntryFinal, or FundingSettlement")
    _text(event.event_id, "event_id")
    _text(event.settlement_id, "settlement_id")
    settlement = _integer(event.settlement_ms, "settlement_ms")
    exchange, received = _times(event.exchange_ms, event.received_ms)
    if settlement != exchange:
        raise AccountingViolation("settlement_ms must equal exchange_ms")
    qty = _decimal(event.qty_at_settlement, "qty_at_settlement", nonnegative=True)
    mark = _decimal(event.mark_price, "mark_price", positive=True)
    rate = _decimal(event.rate, "rate")
    _sha(event.source_sha256, "funding.source_sha256")
    return qty, mark, rate, exchange, received


def _event_fingerprint(event: object) -> tuple[object, ...]:
    if isinstance(event, Execution):
        return ("execution",) + tuple(event.__dict__.values())
    if isinstance(event, EntryFinal):
        return ("entry_final",) + tuple(event.__dict__.values())
    if isinstance(event, FundingSettlement):
        return ("funding",) + tuple(event.__dict__.values())
    raise AccountingViolation("event must be Execution, EntryFinal, or FundingSettlement")


def _execution_fingerprint(event: Execution) -> tuple[object, ...]:
    return tuple(value for key, value in event.__dict__.items() if key != "event_id")


def _funding_fingerprint(event: FundingSettlement) -> tuple[object, ...]:
    return tuple(value for key, value in event.__dict__.items() if key != "event_id")


def replay_accounting(
    plan: AccountingPlan,
    events: tuple[Execution | EntryFinal | FundingSettlement, ...] | list[Execution | EntryFinal | FundingSettlement],
    funding_schedule: FundingSchedule | None,
    *,
    mark_price: str | None = None,
    reconcile_delayed_funding: bool = False,
) -> AccountingResult:
    """Replay cash without moving a receipt into the past.

    Optional funding reconciliation accepts later receipt of settled funding,
    validating its quantity against executions at settlement time. Execution
    exchange order and all receive clocks remain strict. A fill within five
    seconds of settlement makes net costs uncertain in this public simulation.
    """
    if not isinstance(reconcile_delayed_funding, bool):
        raise AccountingViolation("reconcile_delayed_funding must be bool")
    accepted_stop, planned_risk = _validate_plan(plan)
    schedule = _validate_schedule(funding_schedule)
    if not isinstance(events, (tuple, list)):
        raise AccountingViolation("events must be a tuple or list")
    mark = None if mark_price is None else _decimal(mark_price, "mark_price", positive=True)

    held_qty = Fraction(0)
    held_cost = Fraction(0)
    aggregate_qty = Fraction(0)
    aggregate_notional = Fraction(0)
    gross = Fraction(0)
    known_fees = Fraction(0)
    funding = Fraction(0)
    unknown_fee = False
    final_seen = False
    fixed_r0: Fraction | None = None
    issues: set[str] = set()
    event_ids: dict[str, tuple[object, ...]] = {}
    executions: dict[str, tuple[object, ...]] = {}
    settlements: dict[str, tuple[object, ...]] = {}
    seen_settlement_times: set[int] = set()
    last_exchange: int | None = None
    last_received: int | None = None
    first_entry_exchange: int | None = None
    last_execution_exchange: int | None = None
    exposure_changes: list[tuple[int, Fraction]] = []
    delayed_settlements: list[tuple[FundingSettlement, Fraction, Fraction, Fraction]] = []

    for event in events:
        fingerprint = _event_fingerprint(event)
        event_id = getattr(event, "event_id", None)
        _text(event_id, "event_id")
        previous_event = event_ids.get(event_id)
        if previous_event is not None:
            if previous_event == fingerprint:
                continue
            raise AccountingViolation("conflicting event_id reuse")

        duplicate_receipt = False
        if isinstance(event, Execution):
            qty, price, fee, exchange, received = _execution_values(event)
            execution_fingerprint = _execution_fingerprint(event)
            prior_execution = executions.get(event.execution_id)
            if prior_execution is not None:
                if prior_execution != execution_fingerprint:
                    raise AccountingViolation("conflicting execution_id reuse")
                duplicate_receipt = True
        elif isinstance(event, EntryFinal):
            exchange, received = _final_values(event)
            if final_seen:
                raise AccountingViolation("multiple distinct EntryFinal events")
        elif isinstance(event, FundingSettlement):
            qty, price, rate, exchange, received = _funding_values(event)
            settlement_fingerprint = _funding_fingerprint(event)
            prior_settlement = settlements.get(event.settlement_id)
            if prior_settlement is not None:
                if prior_settlement != settlement_fingerprint:
                    raise AccountingViolation("conflicting settlement_id reuse")
                duplicate_receipt = True
        else:
            raise AccountingViolation("event must be Execution, EntryFinal, or FundingSettlement")

        event_ids[event_id] = fingerprint
        if duplicate_receipt:
            continue
        exchange_watermark = last_execution_exchange if reconcile_delayed_funding else last_exchange
        check_exchange = not (reconcile_delayed_funding and isinstance(event, FundingSettlement))
        if check_exchange and exchange_watermark is not None and exchange < exchange_watermark:
            raise AccountingViolation("decreasing exchange timestamps are unresolved")
        if last_received is not None and received < last_received:
            raise AccountingViolation("decreasing received timestamps are unresolved")

        last_exchange = exchange if last_exchange is None else max(last_exchange, exchange)
        last_received = received
        if not isinstance(event, FundingSettlement):
            last_execution_exchange = exchange
        if isinstance(event, Execution):
            exposure_changes.append((exchange, qty if event.kind == "ENTRY" else -qty))
            executions[event.execution_id] = execution_fingerprint
            if fee is None:
                unknown_fee = True
                issues.add("UNKNOWN_FEE")
            else:
                known_fees += fee
            if event.kind == "ENTRY":
                if final_seen:
                    issues.add("FINAL_ENTRY_DRIFT")
                held_qty += qty
                held_cost += qty * price
                aggregate_qty += qty
                aggregate_notional += qty * price
                if first_entry_exchange is None:
                    first_entry_exchange = exchange
            else:
                if qty > held_qty:
                    raise AccountingViolation("exit qty exceeds held qty")
                gross += qty * (held_cost / held_qty - price)
                held_cost -= qty * held_cost / held_qty
                held_qty -= qty
                if held_qty == 0:
                    held_cost = Fraction(0)
        elif isinstance(event, EntryFinal):
            final_seen = True
            if aggregate_qty > 0:
                fixed_r0 = aggregate_qty * abs(aggregate_notional / aggregate_qty - accepted_stop)
        else:
            settlements[event.settlement_id] = settlement_fingerprint
            if event.settlement_ms in seen_settlement_times:
                raise AccountingViolation("multiple funding settlements share one timestamp")
            if not reconcile_delayed_funding and qty != held_qty:
                raise AccountingViolation("funding qty_at_settlement must equal held qty")
            if reconcile_delayed_funding:
                delayed_settlements.append((event, qty, price, rate))
            else:
                funding += qty * price * rate
            seen_settlement_times.add(event.settlement_ms)

    for settlement, qty, price, rate in delayed_settlements:
        historical_qty = sum((change for when, change in exposure_changes
                              if when <= settlement.settlement_ms), Fraction(0))
        if qty != historical_qty:
            raise AccountingViolation("funding qty_at_settlement must equal historical held qty")
        if any(abs(when - settlement.settlement_ms) <= 5000 for when, _ in exposure_changes):
            issues.add("FUNDING_BOUNDARY_AMBIGUOUS")
        funding += qty * price * rate

    coverage_complete = False
    if first_entry_exchange is None:
        coverage_complete = schedule is not None and schedule.complete
    elif schedule is None:
        issues.add("FUNDING_SCHEDULE_MISSING")
    else:
        required = {time for time in schedule.settlement_ms if first_entry_exchange <= time <= last_exchange}
        coverage_complete = (
            schedule.complete
            and schedule.start_ms <= first_entry_exchange
            and schedule.end_ms >= last_exchange
            and seen_settlement_times == required
        )
        if not coverage_complete:
            issues.add("FUNDING_COVERAGE_INCOMPLETE")
    costs_complete = not unknown_fee and coverage_complete and "FUNDING_BOUNDARY_AMBIGUOUS" not in issues
    net_realized = gross - known_fees + funding if costs_complete else None
    unrealized = None if mark is None else held_qty * (held_cost / held_qty - mark) if held_qty else Fraction(0)
    net_equity_change = None
    if costs_complete and (mark is not None or held_qty == 0):
        net_equity_change = net_realized + (unrealized if unrealized is not None else Fraction(0))
    closed_net_r = None
    if (
        final_seen
        and held_qty == 0
        and fixed_r0 is not None
        and fixed_r0 > 0
        and costs_complete
        and not issues
    ):
        closed_net_r = net_realized / fixed_r0
    return AccountingResult(
        held_qty=held_qty,
        remaining_basis=held_cost / held_qty if held_qty else None,
        aggregate_entry_qty=aggregate_qty,
        aggregate_entry_notional=aggregate_notional,
        gross_realized=gross,
        known_fee_total=known_fees,
        settled_funding=funding,
        planned_risk_amount=planned_risk,
        fixed_r0=fixed_r0,
        net_realized=net_realized,
        unrealized=unrealized,
        net_equity_change=net_equity_change,
        closed_net_r=closed_net_r,
        issues=frozenset(issues),
        funding_coverage_complete=coverage_complete,
        costs_complete=costs_complete,
    )
