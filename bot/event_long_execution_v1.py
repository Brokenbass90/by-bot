"""Fail-closed research execution contract for event-driven long plans.

This module is deliberately standalone.  It has no broker, network, sizing,
allocator, or live-router imports.  A frozen long plan is filled only at the
exact first M5 open after its closed M15 signal bar.  The stop never moves;
1R/2R targets are re-anchored to the actual open.  Intrabar ambiguity is
resolved stop-first and adverse stop gaps fill at the actual bar open.

Funding is event based, never smeared over elapsed time.  For a long, a
positive signed funding rate is a debit and a negative rate is a credit.  The
stress scenario discards credits and applies at least a five-basis-point debit
at every positive funding event.  Funding at the entry timestamp is excluded;
later events are applied at the exact M5 open before that bar's price path.
This executor authenticates the events it receives but cannot prove that an
external history omitted none; complete funding coverage is therefore a
mandatory blocker in the eventual performance runner.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple


M5_MS = 300_000
M15_MS = 900_000
SIDE = "long"
SIDE_IDENTITY = "long_only"
CONTRACT_NAME = "event_long_next_open_execution_v1"
PLAN_ID_LENGTH = 32
TRADE_ID_LENGTH = 32

BASE_FEE_BPS_PER_SIDE = 6.0
BASE_SLIPPAGE_BPS_PER_SIDE = 2.0
STRESS_FEE_BPS_PER_SIDE = 10.0
STRESS_SLIPPAGE_BPS_PER_SIDE = 5.0
STRESS_MIN_FUNDING_DEBIT_BPS = 5.0
FUNDING_COMPLETENESS_REQUIREMENT = (
    "the performance runner must prove complete exact-event funding coverage "
    "for every filled holding window before computing metrics"
)


class EventLongExecutionError(ValueError):
    """The supplied research input cannot be evaluated without fabrication."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EventLongExecutionError(f"value is not canonical JSON: {exc}") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_hex(value: object, length: int) -> bool:
    text = str(value or "")
    return len(text) == length and all(char in "0123456789abcdef" for char in text)


def _finite_positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _exact_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EventLongExecutionError(f"{name} must be an exact integer")
    return value


def _plan_payload(plan: "FrozenLongPlanV1") -> dict[str, Any]:
    return {
        "contract": plan.contract,
        "event_id": plan.event_id,
        "level_id": plan.level_id,
        "strategy": plan.strategy,
        "symbol": plan.symbol,
        "side": plan.side,
        "side_identity": plan.side_identity,
        "signal_open_ts": plan.signal_open_ts,
        "signal_known_at_ts": plan.signal_known_at_ts,
        "valid_from_ts": plan.valid_from_ts,
        "entry_reference": plan.entry_reference,
        "frozen_stop": plan.frozen_stop,
        "signal_interval_ms": plan.signal_interval_ms,
        "execution_interval_ms": plan.execution_interval_ms,
        "tp1_rr": plan.tp1_rr,
        "tp1_fraction": plan.tp1_fraction,
        "tp2_rr": plan.tp2_rr,
        "tp2_fraction": plan.tp2_fraction,
        "max_hold_bars": plan.max_hold_bars,
        "source_fingerprint": plan.source_fingerprint,
        "research_only": plan.research_only,
        "broker_calls": plan.broker_calls,
    }


def make_plan_id_from_payload(payload: Mapping[str, Any]) -> str:
    """Return the deterministic identifier for a complete frozen plan payload."""
    return _sha256(dict(payload))[:PLAN_ID_LENGTH]


@dataclass(frozen=True)
class FrozenLongPlanV1:
    """Immutable M15 decision contract; intentionally not a live order."""

    plan_id: str
    event_id: str
    level_id: str
    strategy: str
    symbol: str
    signal_open_ts: int
    signal_known_at_ts: int
    valid_from_ts: int
    entry_reference: float
    frozen_stop: float
    source_fingerprint: str
    contract: str = CONTRACT_NAME
    side: str = SIDE
    side_identity: str = SIDE_IDENTITY
    signal_interval_ms: int = M15_MS
    execution_interval_ms: int = M5_MS
    tp1_rr: float = 1.0
    tp1_fraction: float = 0.5
    tp2_rr: float = 2.0
    tp2_fraction: float = 0.5
    max_hold_bars: int = 96
    research_only: bool = True
    broker_calls: bool = False

    def __post_init__(self) -> None:
        if self.contract != CONTRACT_NAME:
            raise EventLongExecutionError("plan contract identity mismatch")
        if self.side != SIDE or self.side_identity != SIDE_IDENTITY:
            raise EventLongExecutionError("execution contract is physically long-only")
        if not self.research_only or self.broker_calls:
            raise EventLongExecutionError("execution contract must remain research-only")
        if not all((self.event_id, self.level_id, self.strategy, self.symbol)):
            raise EventLongExecutionError("plan identity fields must be non-empty")
        if self.symbol != self.symbol.upper():
            raise EventLongExecutionError("symbol must be canonical uppercase")
        if not _is_hex(self.source_fingerprint, 64):
            raise EventLongExecutionError("source_fingerprint must be a lowercase sha256")
        if self.signal_interval_ms != M15_MS or self.execution_interval_ms != M5_MS:
            raise EventLongExecutionError("v1 requires a closed M15 signal and M5 execution")
        if _exact_int(self.signal_open_ts, "signal_open_ts") < 0 or self.signal_open_ts % M15_MS != 0:
            raise EventLongExecutionError("signal_open_ts must be an M15 candle-open timestamp")
        _exact_int(self.signal_known_at_ts, "signal_known_at_ts")
        _exact_int(self.valid_from_ts, "valid_from_ts")
        if self.signal_known_at_ts != self.signal_open_ts + M15_MS:
            raise EventLongExecutionError("signal_known_at_ts must be the M15 close boundary")
        if self.valid_from_ts != self.signal_known_at_ts:
            raise EventLongExecutionError(
                "valid_from_ts must be the exact M5 open at the closed-M15 known-at boundary"
            )
        if self.valid_from_ts % M5_MS != 0:
            raise EventLongExecutionError("valid_from_ts is off the M5 grid")
        if not (_finite_positive(self.entry_reference) and _finite_positive(self.frozen_stop)):
            raise EventLongExecutionError("entry reference and frozen stop must be positive")
        if self.frozen_stop >= self.entry_reference:
            raise EventLongExecutionError("long frozen stop must be below entry reference")
        if (
            self.tp1_rr != 1.0
            or self.tp2_rr != 2.0
            or self.tp1_fraction != 0.5
            or self.tp2_fraction != 0.5
            or self.tp1_fraction + self.tp2_fraction != 1.0
            or self.max_hold_bars != 96
        ):
            raise EventLongExecutionError("v1 exit contract is frozen at 1R/2R, 50/50, 96 M5 bars")
        expected = make_plan_id_from_payload(_plan_payload(self))
        if self.plan_id != expected:
            raise EventLongExecutionError("plan_id does not bind the complete frozen plan")


def make_frozen_long_plan_v1(
    *,
    event_id: str,
    level_id: str,
    strategy: str,
    symbol: str,
    signal_open_ts: int,
    entry_reference: float,
    frozen_stop: float,
    source_fingerprint: str,
) -> FrozenLongPlanV1:
    """Construct a valid frozen plan and bind every field into ``plan_id``."""
    values = {
        "contract": CONTRACT_NAME,
        "event_id": str(event_id),
        "level_id": str(level_id),
        "strategy": str(strategy),
        "symbol": str(symbol),
        "side": SIDE,
        "side_identity": SIDE_IDENTITY,
        "signal_open_ts": _exact_int(signal_open_ts, "signal_open_ts"),
        "signal_known_at_ts": _exact_int(signal_open_ts, "signal_open_ts") + M15_MS,
        "valid_from_ts": _exact_int(signal_open_ts, "signal_open_ts") + M15_MS,
        "entry_reference": float(entry_reference),
        "frozen_stop": float(frozen_stop),
        "signal_interval_ms": M15_MS,
        "execution_interval_ms": M5_MS,
        "tp1_rr": 1.0,
        "tp1_fraction": 0.5,
        "tp2_rr": 2.0,
        "tp2_fraction": 0.5,
        "max_hold_bars": 96,
        "source_fingerprint": str(source_fingerprint),
        "research_only": True,
        "broker_calls": False,
    }
    return FrozenLongPlanV1(plan_id=make_plan_id_from_payload(values), **values)


def _funding_payload(event: "HistoricalFundingEventV1") -> dict[str, Any]:
    return {
        "symbol": event.symbol,
        "timestamp_ms": event.timestamp_ms,
        "signed_rate": event.signed_rate,
        "source_fingerprint": event.source_fingerprint,
    }


@dataclass(frozen=True)
class HistoricalFundingEventV1:
    """One exact historical settlement; positive rate means longs pay."""

    funding_id: str
    symbol: str
    timestamp_ms: int
    signed_rate: float
    source_fingerprint: str

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise EventLongExecutionError("funding symbol must be canonical uppercase")
        if (
            not isinstance(self.timestamp_ms, int)
            or isinstance(self.timestamp_ms, bool)
            or self.timestamp_ms < 0
            or self.timestamp_ms % M5_MS != 0
        ):
            raise EventLongExecutionError("funding timestamp must be an exact M5-grid event")
        if not math.isfinite(float(self.signed_rate)) or abs(float(self.signed_rate)) > 0.1:
            raise EventLongExecutionError("funding rate is non-finite or outside the safety bound")
        if not _is_hex(self.source_fingerprint, 64):
            raise EventLongExecutionError("funding source fingerprint must be a sha256")
        expected = _sha256(_funding_payload(self))[:32]
        if self.funding_id != expected:
            raise EventLongExecutionError("funding_id does not bind the exact historical event")


def make_historical_funding_event_v1(
    *,
    symbol: str,
    timestamp_ms: int,
    signed_rate: float,
    source_fingerprint: str,
) -> HistoricalFundingEventV1:
    values = {
        "symbol": str(symbol),
        "timestamp_ms": _exact_int(timestamp_ms, "funding timestamp_ms"),
        "signed_rate": float(signed_rate),
        "source_fingerprint": str(source_fingerprint),
    }
    probe = HistoricalFundingEventV1.__new__(HistoricalFundingEventV1)
    for key, value in values.items():
        object.__setattr__(probe, key, value)
    object.__setattr__(probe, "funding_id", "")
    return HistoricalFundingEventV1(
        funding_id=_sha256(_funding_payload(probe))[:32],
        **values,
    )


@dataclass(frozen=True)
class CostLegV1:
    kind: str
    reason: str
    timestamp_ms: int
    fraction: float
    price: float
    unit_r: float
    gross_r: float
    fee_cost_r: float
    slippage_cost_r: float

    def __post_init__(self) -> None:
        allowed_reasons = {
            "entry": {"actual_next_open"},
            "exit": {"stop", "stop_gap", "tp1", "tp2", "max_hold"},
        }
        if self.kind not in allowed_reasons or self.reason not in allowed_reasons[self.kind]:
            raise EventLongExecutionError("cost leg kind/reason is invalid")
        if _exact_int(self.timestamp_ms, "cost leg timestamp_ms") < 0 or self.timestamp_ms % M5_MS != 0:
            raise EventLongExecutionError("cost leg timestamp is off-grid")
        if not 0 < self.fraction <= 1 or not _finite_positive(self.price):
            raise EventLongExecutionError("cost leg fraction/price is invalid")
        if not all(
            math.isfinite(float(value))
            for value in (self.unit_r, self.gross_r, self.fee_cost_r, self.slippage_cost_r)
        ):
            raise EventLongExecutionError("cost leg contains non-finite values")
        if self.fee_cost_r < 0 or self.slippage_cost_r < 0:
            raise EventLongExecutionError("execution costs cannot be credits")
        expected_gross = 0.0 if self.kind == "entry" else self.fraction * self.unit_r
        if not math.isclose(self.gross_r, expected_gross, rel_tol=0.0, abs_tol=1e-12):
            raise EventLongExecutionError("cost leg gross_r does not reconcile")


@dataclass(frozen=True)
class FundingChargeV1:
    funding_id: str
    timestamp_ms: int
    position_fraction: float
    mark_price: float
    actual_signed_rate: float
    applied_signed_rate: float
    funding_pnl_r: float

    def __post_init__(self) -> None:
        if not _is_hex(self.funding_id, 32):
            raise EventLongExecutionError("funding charge has an invalid event id")
        if (
            not isinstance(self.timestamp_ms, int)
            or isinstance(self.timestamp_ms, bool)
            or self.timestamp_ms < 0
            or self.timestamp_ms % M5_MS != 0
        ):
            raise EventLongExecutionError("funding charge timestamp is invalid")
        if not 0 < self.position_fraction <= 1 or not _finite_positive(self.mark_price):
            raise EventLongExecutionError("funding charge fraction/mark is invalid")
        if not all(
            math.isfinite(float(value))
            for value in (
                self.actual_signed_rate,
                self.applied_signed_rate,
                self.funding_pnl_r,
            )
        ):
            raise EventLongExecutionError("funding charge contains non-finite values")
        if abs(self.actual_signed_rate) > 0.1 or abs(self.applied_signed_rate) > 0.1:
            raise EventLongExecutionError("funding charge rate is outside the safety bound")


def make_trade_id(plan_id: str, entry_ts: int, entry_price: float) -> str:
    if not _is_hex(plan_id, PLAN_ID_LENGTH):
        raise EventLongExecutionError("trade_id requires a valid plan_id")
    return _sha256(
        {
            "contract": CONTRACT_NAME,
            "plan_id": plan_id,
            "entry_ts": _exact_int(entry_ts, "trade entry_ts"),
            "entry": float(entry_price),
        }
    )[:TRADE_ID_LENGTH]


def _receipt_payload(receipt: "TradeReceiptV1") -> dict[str, Any]:
    out = asdict(receipt)
    out.pop("receipt_sha256", None)
    return out


@dataclass(frozen=True)
class TradeReceiptV1:
    """Immutable result for a fill, rejection, closure, or censored path."""

    contract: str
    plan_id: str
    trade_id: Optional[str]
    event_id: str
    strategy: str
    symbol: str
    side: str
    scenario: str
    status: str
    reason: str
    signal_open_ts: int
    signal_known_at_ts: int
    valid_from_ts: int
    entry_ts: Optional[int]
    exit_ts: Optional[int]
    entry_price: Optional[float]
    frozen_stop: float
    target_1: Optional[float]
    target_2: Optional[float]
    initial_risk: Optional[float]
    bars_held: int
    remaining_fraction: float
    exit_reason: Optional[str]
    cost_legs: Tuple[CostLegV1, ...]
    funding_charges: Tuple[FundingChargeV1, ...]
    gross_r: float
    fee_cost_r: float
    slippage_cost_r: float
    funding_pnl_r: float
    net_r: float
    receipt_sha256: str

    def __post_init__(self) -> None:
        if self.contract != CONTRACT_NAME or self.side != SIDE:
            raise EventLongExecutionError("receipt contract/side identity mismatch")
        if not _is_hex(self.plan_id, PLAN_ID_LENGTH):
            raise EventLongExecutionError("receipt has an invalid plan_id")
        if self.scenario not in {"base", "stress"}:
            raise EventLongExecutionError("receipt scenario must be base or stress")
        allowed_statuses = {
            "filled_closed",
            "censored_snapshot_end",
            "rejected_missing_exact_next_open",
            "rejected_gap_through_frozen_stop",
        }
        if self.status not in allowed_statuses or not self.reason:
            raise EventLongExecutionError("receipt status/reason is invalid")
        if not self.event_id or not self.strategy or not self.symbol:
            raise EventLongExecutionError("receipt strategy identity is incomplete")
        if self.symbol != self.symbol.upper() or not _finite_positive(self.frozen_stop):
            raise EventLongExecutionError("receipt symbol/stop is invalid")
        _exact_int(self.signal_open_ts, "receipt signal_open_ts")
        _exact_int(self.signal_known_at_ts, "receipt signal_known_at_ts")
        _exact_int(self.valid_from_ts, "receipt valid_from_ts")
        if (
            self.signal_open_ts < 0
            or self.signal_open_ts % M15_MS != 0
            or self.signal_known_at_ts != self.signal_open_ts + M15_MS
            or self.valid_from_ts != self.signal_known_at_ts
        ):
            raise EventLongExecutionError("receipt decision timeline is invalid")
        if not isinstance(self.bars_held, int) or not 0 <= self.bars_held <= 96:
            raise EventLongExecutionError("receipt bars_held is invalid")
        if self.trade_id is None:
            if self.entry_ts is not None or self.entry_price is not None:
                raise EventLongExecutionError("unfilled receipt cannot carry entry identity")
        else:
            if self.entry_ts is None or self.entry_price is None:
                raise EventLongExecutionError("filled receipt is missing entry identity")
            if self.trade_id != make_trade_id(self.plan_id, self.entry_ts, self.entry_price):
                raise EventLongExecutionError("trade_id does not bind plan and actual fill")
            if (
                self.entry_ts != self.valid_from_ts
                or self.entry_ts % M5_MS != 0
                or not _finite_positive(self.entry_price)
                or self.entry_price <= self.frozen_stop
            ):
                raise EventLongExecutionError("filled receipt entry geometry is invalid")
            expected_risk = self.entry_price - self.frozen_stop
            if not all(
                _finite_positive(value)
                for value in (self.initial_risk, self.target_1, self.target_2)
            ):
                raise EventLongExecutionError("filled receipt is missing R geometry")
            if not (
                math.isclose(
                    self.initial_risk, expected_risk, rel_tol=0.0, abs_tol=1e-12
                )
                and math.isclose(
                    self.target_1,
                    self.entry_price + expected_risk,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                and math.isclose(
                    self.target_2,
                    self.entry_price + 2.0 * expected_risk,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ):
                raise EventLongExecutionError(
                    "filled receipt targets are not re-anchored to actual open"
                )
        if not 0 <= self.remaining_fraction <= 1:
            raise EventLongExecutionError("receipt remaining fraction is invalid")
        if self.status.startswith("rejected_"):
            if any(
                value is not None
                for value in (
                    self.trade_id,
                    self.entry_ts,
                    self.exit_ts,
                    self.entry_price,
                    self.target_1,
                    self.target_2,
                    self.initial_risk,
                    self.exit_reason,
                )
            ) or self.bars_held != 0 or self.remaining_fraction != 0:
                raise EventLongExecutionError(
                    "rejected receipt contains fabricated trade state"
                )
            if self.cost_legs or self.funding_charges:
                raise EventLongExecutionError(
                    "rejected receipt cannot contain costs or funding"
                )
        elif self.status == "filled_closed":
            allowed_exit_reasons = {
                "stop",
                "stop_gap",
                "tp1_then_stop",
                "tp1_then_stop_gap",
                "tp1_tp2",
                "max_hold",
                "tp1_then_max_hold",
            }
            if (
                self.trade_id is None
                or self.exit_ts is None
                or self.exit_reason not in allowed_exit_reasons
                or self.remaining_fraction != 0
                or not 1 <= self.bars_held <= 96
                or self.reason != self.exit_reason
            ):
                raise EventLongExecutionError("closed receipt lifecycle is inconsistent")
        elif self.status == "censored_snapshot_end":
            if (
                self.trade_id is None
                or self.exit_ts is not None
                or self.exit_reason is not None
                or not 0 < self.remaining_fraction <= 1
                or not 1 <= self.bars_held < 96
                or self.reason != "fewer than 96 closed M5 bars are available"
            ):
                raise EventLongExecutionError("censored receipt lifecycle is inconsistent")
        expected_rejection_reasons = {
            "rejected_missing_exact_next_open": "the exact valid_from M5 open is absent",
            "rejected_gap_through_frozen_stop": (
                "actual next open is at or through the frozen long stop"
            ),
        }
        if self.status in expected_rejection_reasons and (
            self.reason != expected_rejection_reasons[self.status]
        ):
            raise EventLongExecutionError("rejected receipt reason is not canonical")
        if self.exit_ts is not None and (
            self.exit_ts < self.valid_from_ts
            or self.exit_ts % M5_MS != 0
            or self.exit_ts != self.valid_from_ts + (self.bars_held - 1) * M5_MS
        ):
            raise EventLongExecutionError("receipt exit timeline is inconsistent")
        if any(not isinstance(leg, CostLegV1) for leg in self.cost_legs):
            raise EventLongExecutionError("receipt contains an invalid cost leg")
        if any(
            not isinstance(charge, FundingChargeV1) for charge in self.funding_charges
        ):
            raise EventLongExecutionError("receipt contains an invalid funding charge")
        for leg in self.cost_legs:
            leg.__post_init__()
        for charge in self.funding_charges:
            charge.__post_init__()
        if self.trade_id is not None:
            if not self.cost_legs or self.cost_legs[0].kind != "entry":
                raise EventLongExecutionError(
                    "filled receipt must start with one entry cost leg"
                )
            if (
                self.cost_legs[0].fraction != 1.0
                or self.cost_legs[0].timestamp_ms != self.entry_ts
            ):
                raise EventLongExecutionError(
                    "entry cost leg does not match the actual fill"
                )
            exited_fraction = sum(
                leg.fraction for leg in self.cost_legs if leg.kind == "exit"
            )
            if not math.isclose(
                exited_fraction + self.remaining_fraction,
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise EventLongExecutionError("exit leg fractions do not reconcile")
            expected_fee_bps, expected_slippage_bps = _cost_parameters(self.scenario)
            for leg in self.cost_legs:
                notional_to_r = leg.fraction * leg.price / self.initial_risk
                expected_fee = expected_fee_bps / 10_000.0 * notional_to_r
                expected_slippage = (
                    expected_slippage_bps / 10_000.0 * notional_to_r
                )
                if not math.isclose(
                    leg.fee_cost_r,
                    expected_fee,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ) or not math.isclose(
                    leg.slippage_cost_r,
                    expected_slippage,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise EventLongExecutionError(
                        "cost leg does not match the frozen scenario"
                    )
            for charge in self.funding_charges:
                expected_applied = charge.actual_signed_rate
                if self.scenario == "stress":
                    expected_applied = (
                        max(
                            charge.actual_signed_rate,
                            STRESS_MIN_FUNDING_DEBIT_BPS / 10_000.0,
                        )
                        if charge.actual_signed_rate > 0
                        else 0.0
                    )
                expected_funding_r = (
                    -expected_applied
                    * charge.position_fraction
                    * charge.mark_price
                    / self.initial_risk
                )
                if not math.isclose(
                    charge.applied_signed_rate,
                    expected_applied,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                ) or not math.isclose(
                    charge.funding_pnl_r,
                    expected_funding_r,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise EventLongExecutionError(
                        "funding charge violates the scenario policy"
                    )
        numeric = (
            self.gross_r,
            self.fee_cost_r,
            self.slippage_cost_r,
            self.funding_pnl_r,
            self.net_r,
        )
        if not all(math.isfinite(float(value)) for value in numeric):
            raise EventLongExecutionError("receipt summary contains non-finite values")
        if self.fee_cost_r < 0 or self.slippage_cost_r < 0:
            raise EventLongExecutionError("receipt execution costs cannot be negative")
        if not math.isclose(
            self.gross_r,
            sum(leg.gross_r for leg in self.cost_legs),
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.fee_cost_r,
            sum(leg.fee_cost_r for leg in self.cost_legs),
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.slippage_cost_r,
            sum(leg.slippage_cost_r for leg in self.cost_legs),
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.funding_pnl_r,
            sum(charge.funding_pnl_r for charge in self.funding_charges),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise EventLongExecutionError(
                "receipt leg/funding totals do not reconcile"
            )
        expected_net = self.gross_r - self.fee_cost_r - self.slippage_cost_r + self.funding_pnl_r
        if not math.isclose(self.net_r, expected_net, rel_tol=0.0, abs_tol=1e-12):
            raise EventLongExecutionError("receipt net_r does not reconcile")
        if self.receipt_sha256 != _sha256(_receipt_payload(self)):
            raise EventLongExecutionError("receipt checksum mismatch")


def _make_receipt(**values: Any) -> TradeReceiptV1:
    probe = TradeReceiptV1.__new__(TradeReceiptV1)
    for key, value in values.items():
        object.__setattr__(probe, key, value)
    object.__setattr__(probe, "receipt_sha256", "")
    return TradeReceiptV1(
        **values,
        receipt_sha256=_sha256(_receipt_payload(probe)),
    )


def _validate_rows(
    rows: Sequence[Sequence[Any]], *, as_of_ms: int
) -> list[tuple[int, float, float, float, float, float]]:
    if int(as_of_ms) != as_of_ms or as_of_ms < 0:
        raise EventLongExecutionError("as_of_ms must be a non-negative integer")
    out: list[tuple[int, float, float, float, float, float]] = []
    previous: Optional[int] = None
    for raw in rows:
        if len(raw) < 6:
            raise EventLongExecutionError("M5 row must contain ts,o,h,l,c,v")
        try:
            raw_ts = float(raw[0])
            ts = int(raw_ts)
            values = tuple(float(raw[index]) for index in range(1, 6))
        except (TypeError, ValueError) as exc:
            raise EventLongExecutionError("M5 row contains invalid values") from exc
        if not math.isfinite(raw_ts) or raw_ts != ts or ts < 0 or ts % M5_MS != 0:
            raise EventLongExecutionError("M5 row timestamp is invalid or off-grid")
        if previous is not None and ts != previous + M5_MS:
            raise EventLongExecutionError("closed M5 input is duplicate, unordered, or gappy")
        if ts + M5_MS > int(as_of_ms):
            raise EventLongExecutionError("open or future M5 bars are forbidden")
        o, h, l, c, v = values
        if not all(math.isfinite(value) for value in values):
            raise EventLongExecutionError("M5 row contains non-finite values")
        if min(o, h, l, c) <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c, h):
            raise EventLongExecutionError("M5 row has invalid OHLCV geometry")
        out.append((ts, o, h, l, c, v))
        previous = ts
    return out


def _validate_funding_events(
    events: Sequence[HistoricalFundingEventV1],
    *,
    symbol: str,
    as_of_ms: int,
) -> dict[int, HistoricalFundingEventV1]:
    by_ts: dict[int, HistoricalFundingEventV1] = {}
    previous: Optional[int] = None
    for event in events:
        if not isinstance(event, HistoricalFundingEventV1):
            raise EventLongExecutionError("funding input must contain frozen V1 events")
        # Re-run the identity check in case an unsafe caller bypassed construction.
        event.__post_init__()
        if event.symbol != symbol:
            raise EventLongExecutionError("funding symbol does not match the plan")
        if event.timestamp_ms > int(as_of_ms):
            raise EventLongExecutionError("future funding events are forbidden")
        if previous is not None and event.timestamp_ms <= previous:
            raise EventLongExecutionError("funding events must be strictly ordered and unique")
        by_ts[event.timestamp_ms] = event
        previous = event.timestamp_ms
    return by_ts


def _cost_parameters(scenario: str) -> tuple[float, float]:
    if scenario == "base":
        return BASE_FEE_BPS_PER_SIDE, BASE_SLIPPAGE_BPS_PER_SIDE
    if scenario == "stress":
        return STRESS_FEE_BPS_PER_SIDE, STRESS_SLIPPAGE_BPS_PER_SIDE
    raise EventLongExecutionError("scenario must be exactly 'base' or 'stress'")


def _cost_leg(
    *,
    kind: str,
    reason: str,
    ts: int,
    fraction: float,
    price: float,
    unit_r: float,
    risk: float,
    fee_bps: float,
    slippage_bps: float,
) -> CostLegV1:
    gross_r = 0.0 if kind == "entry" else fraction * unit_r
    notional_to_r = fraction * price / risk
    return CostLegV1(
        kind=kind,
        reason=reason,
        timestamp_ms=ts,
        fraction=fraction,
        price=price,
        unit_r=unit_r,
        gross_r=gross_r,
        fee_cost_r=fee_bps / 10_000.0 * notional_to_r,
        slippage_cost_r=slippage_bps / 10_000.0 * notional_to_r,
    )


def _funding_charge(
    event: HistoricalFundingEventV1,
    *,
    scenario: str,
    position_fraction: float,
    mark_price: float,
    risk: float,
) -> FundingChargeV1:
    actual = float(event.signed_rate)
    if scenario == "base":
        applied = actual
    elif actual > 0:
        applied = max(actual, STRESS_MIN_FUNDING_DEBIT_BPS / 10_000.0)
    else:
        applied = 0.0
    pnl_r = -applied * position_fraction * mark_price / risk
    return FundingChargeV1(
        funding_id=event.funding_id,
        timestamp_ms=event.timestamp_ms,
        position_fraction=position_fraction,
        mark_price=mark_price,
        actual_signed_rate=actual,
        applied_signed_rate=applied,
        funding_pnl_r=pnl_r,
    )


def simulate_frozen_long_plan_v1(
    plan: FrozenLongPlanV1,
    closed_m5_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    funding_events: Sequence[HistoricalFundingEventV1] = (),
    scenario: str = "base",
) -> TradeReceiptV1:
    """Evaluate one frozen plan without mutating state or touching a broker.

    The caller/performance runner must separately prove
    :data:`FUNDING_COMPLETENESS_REQUIREMENT`; this pure function can validate
    exact supplied events, but cannot prove that an external source omitted no
    settlement.
    """
    if not isinstance(plan, FrozenLongPlanV1):
        raise EventLongExecutionError("plan must be a FrozenLongPlanV1")
    plan.__post_init__()
    fee_bps, slippage_bps = _cost_parameters(scenario)
    rows = _validate_rows(closed_m5_rows, as_of_ms=as_of_ms)
    funding_by_ts = _validate_funding_events(
        funding_events, symbol=plan.symbol, as_of_ms=as_of_ms
    )
    index_by_ts = {row[0]: index for index, row in enumerate(rows)}
    entry_index = index_by_ts.get(plan.valid_from_ts)

    common = {
        "contract": CONTRACT_NAME,
        "plan_id": plan.plan_id,
        "event_id": plan.event_id,
        "strategy": plan.strategy,
        "symbol": plan.symbol,
        "side": SIDE,
        "scenario": scenario,
        "signal_open_ts": plan.signal_open_ts,
        "signal_known_at_ts": plan.signal_known_at_ts,
        "valid_from_ts": plan.valid_from_ts,
        "frozen_stop": plan.frozen_stop,
    }
    if entry_index is None:
        return _make_receipt(
            **common,
            trade_id=None,
            status="rejected_missing_exact_next_open",
            reason="the exact valid_from M5 open is absent",
            entry_ts=None,
            exit_ts=None,
            entry_price=None,
            target_1=None,
            target_2=None,
            initial_risk=None,
            bars_held=0,
            remaining_fraction=0.0,
            exit_reason=None,
            cost_legs=(),
            funding_charges=(),
            gross_r=0.0,
            fee_cost_r=0.0,
            slippage_cost_r=0.0,
            funding_pnl_r=0.0,
            net_r=0.0,
        )

    entry_ts, entry, _, _, _, _ = rows[entry_index]
    if entry <= plan.frozen_stop:
        return _make_receipt(
            **common,
            trade_id=None,
            status="rejected_gap_through_frozen_stop",
            reason="actual next open is at or through the frozen long stop",
            entry_ts=None,
            exit_ts=None,
            entry_price=None,
            target_1=None,
            target_2=None,
            initial_risk=None,
            bars_held=0,
            remaining_fraction=0.0,
            exit_reason=None,
            cost_legs=(),
            funding_charges=(),
            gross_r=0.0,
            fee_cost_r=0.0,
            slippage_cost_r=0.0,
            funding_pnl_r=0.0,
            net_r=0.0,
        )

    risk = entry - plan.frozen_stop
    target_1 = entry + risk
    target_2 = entry + 2.0 * risk
    trade_id = make_trade_id(plan.plan_id, entry_ts, entry)
    cost_legs: list[CostLegV1] = [
        _cost_leg(
            kind="entry",
            reason="actual_next_open",
            ts=entry_ts,
            fraction=1.0,
            price=entry,
            unit_r=0.0,
            risk=risk,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
    ]
    charges: list[FundingChargeV1] = []
    remaining = 1.0
    tp1_done = False
    exit_ts: Optional[int] = None
    exit_reason: Optional[str] = None
    bars_held = 0

    last_index = min(len(rows) - 1, entry_index + plan.max_hold_bars - 1)
    for offset, index in enumerate(range(entry_index, last_index + 1), start=1):
        ts, open_, high, low, close, _ = rows[index]
        bars_held = offset

        # Entry at the settlement timestamp occurs after that settlement.  On
        # later bars, the position existed before the exact funding event and
        # funding is applied before any intrabar exit on that timestamp.
        funding_event = funding_by_ts.get(ts) if ts > entry_ts else None
        if funding_event is not None:
            charges.append(
                _funding_charge(
                    funding_event,
                    scenario=scenario,
                    position_fraction=remaining,
                    mark_price=open_,
                    risk=risk,
                )
            )

        # Stop first on every bar.  A later open below the frozen stop is an
        # adverse gap fill at that actual open, never at the ideal stop.
        if open_ <= plan.frozen_stop or low <= plan.frozen_stop:
            fill = open_ if open_ <= plan.frozen_stop else plan.frozen_stop
            reason = "stop_gap" if fill < plan.frozen_stop else "stop"
            unit_r = (fill - entry) / risk
            cost_legs.append(
                _cost_leg(
                    kind="exit",
                    reason=reason,
                    ts=ts,
                    fraction=remaining,
                    price=fill,
                    unit_r=unit_r,
                    risk=risk,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                )
            )
            exit_ts = ts
            exit_reason = reason if not tp1_done else f"tp1_then_{reason}"
            remaining = 0.0
            break

        if not tp1_done and high >= target_2:
            for fraction, price, reason, unit_r in (
                (0.5, target_1, "tp1", 1.0),
                (0.5, target_2, "tp2", 2.0),
            ):
                cost_legs.append(
                    _cost_leg(
                        kind="exit",
                        reason=reason,
                        ts=ts,
                        fraction=fraction,
                        price=price,
                        unit_r=unit_r,
                        risk=risk,
                        fee_bps=fee_bps,
                        slippage_bps=slippage_bps,
                    )
                )
            remaining = 0.0
            exit_ts = ts
            exit_reason = "tp1_tp2"
            break
        if not tp1_done and high >= target_1:
            tp1_done = True
            remaining = 0.5
            cost_legs.append(
                _cost_leg(
                    kind="exit",
                    reason="tp1",
                    ts=ts,
                    fraction=0.5,
                    price=target_1,
                    unit_r=1.0,
                    risk=risk,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                )
            )
        elif tp1_done and high >= target_2:
            cost_legs.append(
                _cost_leg(
                    kind="exit",
                    reason="tp2",
                    ts=ts,
                    fraction=0.5,
                    price=target_2,
                    unit_r=2.0,
                    risk=risk,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                )
            )
            remaining = 0.0
            exit_ts = ts
            exit_reason = "tp1_tp2"
            break

        if offset == plan.max_hold_bars:
            cost_legs.append(
                _cost_leg(
                    kind="exit",
                    reason="max_hold",
                    ts=ts,
                    fraction=remaining,
                    price=close,
                    unit_r=(close - entry) / risk,
                    risk=risk,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                )
            )
            remaining = 0.0
            exit_ts = ts
            exit_reason = "tp1_then_max_hold" if tp1_done else "max_hold"
            break

    gross_r = sum(leg.gross_r for leg in cost_legs)
    fee_cost_r = sum(leg.fee_cost_r for leg in cost_legs)
    slippage_cost_r = sum(leg.slippage_cost_r for leg in cost_legs)
    funding_pnl_r = sum(charge.funding_pnl_r for charge in charges)
    net_r = gross_r - fee_cost_r - slippage_cost_r + funding_pnl_r
    status = "filled_closed" if remaining == 0 else "censored_snapshot_end"
    reason = exit_reason or "fewer than 96 closed M5 bars are available"
    return _make_receipt(
        **common,
        trade_id=trade_id,
        status=status,
        reason=reason,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry_price=entry,
        target_1=target_1,
        target_2=target_2,
        initial_risk=risk,
        bars_held=bars_held,
        remaining_fraction=remaining,
        exit_reason=exit_reason,
        cost_legs=tuple(cost_legs),
        funding_charges=tuple(charges),
        gross_r=gross_r,
        fee_cost_r=fee_cost_r,
        slippage_cost_r=slippage_cost_r,
        funding_pnl_r=funding_pnl_r,
        net_r=net_r,
    )


def verify_trade_receipt_v1(receipt: TradeReceiptV1) -> None:
    """Fail closed if any receipt field or deterministic identifier was altered."""
    if not isinstance(receipt, TradeReceiptV1):
        raise EventLongExecutionError("receipt must be a TradeReceiptV1")
    receipt.__post_init__()


__all__ = [
    "BASE_FEE_BPS_PER_SIDE",
    "BASE_SLIPPAGE_BPS_PER_SIDE",
    "CONTRACT_NAME",
    "CostLegV1",
    "EventLongExecutionError",
    "FUNDING_COMPLETENESS_REQUIREMENT",
    "FrozenLongPlanV1",
    "FundingChargeV1",
    "HistoricalFundingEventV1",
    "M5_MS",
    "M15_MS",
    "STRESS_FEE_BPS_PER_SIDE",
    "STRESS_MIN_FUNDING_DEBIT_BPS",
    "STRESS_SLIPPAGE_BPS_PER_SIDE",
    "TradeReceiptV1",
    "make_frozen_long_plan_v1",
    "make_historical_funding_event_v1",
    "make_trade_id",
    "simulate_frozen_long_plan_v1",
    "verify_trade_receipt_v1",
]
