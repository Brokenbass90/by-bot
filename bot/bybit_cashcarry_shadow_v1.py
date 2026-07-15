"""Research-only Bybit spot/perpetual cash-and-carry paper shadow.

This module deliberately has no authenticated exchange client and no order API.
It consumes normalized PUBLIC quotes/funding observations and simulates one
positive-carry construction only:

    long spot + short USDT linear perpetual, equal USD notional per leg.

The implementation is intentionally conservative:

* entry needs at least three distinct, completed, positive funding settlements;
* every entry/exit uses executable top-of-book prices plus adverse slippage;
* all four fills and both fee schedules are recorded;
* funding is booked only after its settlement timestamp and only with a
  contemporaneous public perp-price proxy;
* incomplete/stale/crossed/thin observations are refused, never partially
  fabricated;
* terminal cycle receipts are checksummed and stored append-only/idempotently.

It is mechanics evidence, not evidence of an edge and not a live executor.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


SCHEMA_ID = "bybit_cashcarry_shadow_cycle_v1"
OBSERVATION_SCHEMA_ID = "bybit_public_cashcarry_observation_v1"
SOURCE_ID = "bybit_public_v5"
DAY_MS = 24 * 60 * 60 * 1000


class CashCarryShadowError(ValueError):
    """Raised when the research contract cannot be satisfied safely."""


def _finite(value: Any, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise CashCarryShadowError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise CashCarryShadowError(f"{name} must be finite")
    return out


def _positive(value: Any, name: str) -> float:
    out = _finite(value, name)
    if out <= 0:
        raise CashCarryShadowError(f"{name} must be positive")
    return out


def _exact_ms(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CashCarryShadowError(f"{name} must be an integer timestamp")
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise CashCarryShadowError(f"{name} must be an integer timestamp") from exc
    if out < 0 or float(value) != float(out):
        raise CashCarryShadowError(f"{name} must be a non-negative exact integer")
    return out


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rounded(value: float) -> float:
    return round(float(value), 12)


def _basis_fraction(spot_mid: float, perp_mid: float) -> float:
    return (perp_mid - spot_mid) / spot_mid


@dataclass(frozen=True)
class FundingSettlement:
    """A completed public funding observation.

    ``perp_mark_price`` is optional for pre-entry persistence.  It is mandatory
    if a position was open at this settlement because a cash amount otherwise
    cannot be computed without inventing a valuation price.
    """

    settled_at_ms: int
    rate: float
    perp_mark_price: Optional[float] = None

    def __post_init__(self) -> None:
        _exact_ms(self.settled_at_ms, "settled_at_ms")
        _finite(self.rate, "funding rate")
        if self.perp_mark_price is not None:
            _positive(self.perp_mark_price, "funding perp_mark_price")

    @property
    def settlement_id(self) -> str:
        # The exchange settlement identity does not depend on a later valuation
        # proxy.  Repeated public-history rows therefore deduplicate correctly.
        return _sha256({"settled_at_ms": self.settled_at_ms, "rate": self.rate})


@dataclass(frozen=True)
class PublicQuoteObservation:
    symbol: str
    observed_at_ms: int
    spot_quote_ts_ms: int
    perp_quote_ts_ms: int
    spot_bid: float
    spot_ask: float
    spot_bid_qty: float
    spot_ask_qty: float
    perp_bid: float
    perp_ask: float
    perp_bid_qty: float
    perp_ask_qty: float
    projected_funding_rate: float
    next_funding_time_ms: int
    funding_settlements: tuple[FundingSettlement, ...] = ()
    complete: bool = True
    source: str = SOURCE_ID

    def __post_init__(self) -> None:
        symbol = str(self.symbol).strip().upper()
        if not symbol or not symbol.endswith("USDT"):
            raise CashCarryShadowError("symbol must be an explicit USDT market")
        object.__setattr__(self, "symbol", symbol)
        _exact_ms(self.observed_at_ms, "observed_at_ms")
        _exact_ms(self.spot_quote_ts_ms, "spot_quote_ts_ms")
        _exact_ms(self.perp_quote_ts_ms, "perp_quote_ts_ms")
        _exact_ms(self.next_funding_time_ms, "next_funding_time_ms")
        for name in (
            "spot_bid", "spot_ask", "spot_bid_qty", "spot_ask_qty",
            "perp_bid", "perp_ask", "perp_bid_qty", "perp_ask_qty",
        ):
            _positive(getattr(self, name), name)
        _finite(self.projected_funding_rate, "projected_funding_rate")
        if self.spot_bid > self.spot_ask or self.perp_bid > self.perp_ask:
            raise CashCarryShadowError("crossed/reversed quote")
        if not isinstance(self.complete, bool):
            raise CashCarryShadowError("complete must be boolean")
        if self.source != SOURCE_ID:
            raise CashCarryShadowError("only the frozen public Bybit source is accepted")
        settlements = tuple(self.funding_settlements)
        if any(not isinstance(x, FundingSettlement) for x in settlements):
            raise CashCarryShadowError("funding_settlements must contain FundingSettlement")
        if list(settlements) != sorted(settlements, key=lambda x: x.settled_at_ms):
            raise CashCarryShadowError("funding settlements must be timestamp sorted")
        if len({x.settlement_id for x in settlements}) != len(settlements):
            raise CashCarryShadowError("duplicate funding settlements in one observation")
        if len({x.settled_at_ms for x in settlements}) != len(settlements):
            raise CashCarryShadowError("multiple funding rates for one settlement timestamp")
        if any(x.settled_at_ms > self.observed_at_ms for x in settlements):
            raise CashCarryShadowError("future funding settlement is forbidden")
        if self.next_funding_time_ms <= self.observed_at_ms:
            raise CashCarryShadowError("next funding time must be strictly in the future")
        object.__setattr__(self, "funding_settlements", settlements)

    @property
    def spot_mid(self) -> float:
        return (self.spot_bid + self.spot_ask) / 2.0

    @property
    def perp_mid(self) -> float:
        return (self.perp_bid + self.perp_ask) / 2.0

    @property
    def basis_fraction(self) -> float:
        return _basis_fraction(self.spot_mid, self.perp_mid)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_id": OBSERVATION_SCHEMA_ID,
            "source": self.source,
            "symbol": self.symbol,
            "observed_at_ms": self.observed_at_ms,
            "spot_quote_ts_ms": self.spot_quote_ts_ms,
            "perp_quote_ts_ms": self.perp_quote_ts_ms,
            "spot": {
                "bid": self.spot_bid,
                "ask": self.spot_ask,
                "bid_qty": self.spot_bid_qty,
                "ask_qty": self.spot_ask_qty,
            },
            "perp": {
                "bid": self.perp_bid,
                "ask": self.perp_ask,
                "bid_qty": self.perp_bid_qty,
                "ask_qty": self.perp_ask_qty,
            },
            "projected_funding_rate": self.projected_funding_rate,
            "next_funding_time_ms": self.next_funding_time_ms,
            "funding_settlements": [dataclasses.asdict(x) for x in self.funding_settlements],
            "complete": self.complete,
        }

    @property
    def observation_id(self) -> str:
        return _sha256(self.payload())

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "PublicQuoteObservation":
        spot = row.get("spot") or {}
        perp = row.get("perp") or {}
        settlements = tuple(
            FundingSettlement(
                settled_at_ms=item["settled_at_ms"],
                rate=item["rate"],
                perp_mark_price=item.get("perp_mark_price"),
            )
            for item in (row.get("funding_settlements") or [])
        )
        return cls(
            symbol=row["symbol"],
            observed_at_ms=row["observed_at_ms"],
            spot_quote_ts_ms=row["spot_quote_ts_ms"],
            perp_quote_ts_ms=row["perp_quote_ts_ms"],
            spot_bid=spot["bid"],
            spot_ask=spot["ask"],
            spot_bid_qty=spot["bid_qty"],
            spot_ask_qty=spot["ask_qty"],
            perp_bid=perp["bid"],
            perp_ask=perp["ask"],
            perp_bid_qty=perp["bid_qty"],
            perp_ask_qty=perp["ask_qty"],
            projected_funding_rate=row["projected_funding_rate"],
            next_funding_time_ms=row["next_funding_time_ms"],
            funding_settlements=settlements,
            complete=row.get("complete", True),
            source=row.get("source", SOURCE_ID),
        )


@dataclass(frozen=True)
class ShadowConfig:
    """Frozen mechanics configuration.  Disabled is the production default."""

    enabled: bool = False
    target_notional_usd: float = 100.0
    min_completed_funding_observations: int = 3
    min_entry_funding_rate: float = 0.00005  # fraction per settlement (0.005%)
    funding_flip_exit_rate: float = 0.0
    spot_fee_bps: float = 10.0
    perp_fee_bps: float = 5.5
    slippage_bps_per_fill: float = 2.0
    max_quote_age_ms: int = 5_000
    max_quote_skew_ms: int = 3_000
    max_funding_valuation_lag_ms: int = 120_000
    max_latest_completed_funding_age_ms: int = 12 * 60 * 60 * 1000
    max_funding_persistence_span_ms: int = 3 * DAY_MS
    max_entry_abs_basis_bps: float = 75.0
    max_live_abs_basis_bps: float = 125.0
    max_adverse_basis_widen_bps: float = 50.0
    max_delta_drift_bps: float = 100.0
    max_hold_ms: int = 14 * DAY_MS

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise CashCarryShadowError("enabled must be boolean")
        _positive(self.target_notional_usd, "target_notional_usd")
        if (
            isinstance(self.min_completed_funding_observations, bool)
            or int(self.min_completed_funding_observations) != float(self.min_completed_funding_observations)
            or int(self.min_completed_funding_observations) < 3
        ):
            raise CashCarryShadowError("at least three completed funding observations are mandatory")
        for name in (
            "min_entry_funding_rate", "spot_fee_bps", "perp_fee_bps",
            "slippage_bps_per_fill", "max_entry_abs_basis_bps",
            "max_live_abs_basis_bps", "max_adverse_basis_widen_bps",
            "max_delta_drift_bps",
        ):
            if _finite(getattr(self, name), name) < 0:
                raise CashCarryShadowError(f"{name} cannot be negative")
        _finite(self.funding_flip_exit_rate, "funding_flip_exit_rate")
        if self.funding_flip_exit_rate >= self.min_entry_funding_rate:
            raise CashCarryShadowError("funding flip exit must be below the entry funding minimum")
        for name in (
            "max_quote_age_ms", "max_quote_skew_ms",
            "max_funding_valuation_lag_ms", "max_latest_completed_funding_age_ms",
            "max_funding_persistence_span_ms", "max_hold_ms",
        ):
            if _exact_ms(getattr(self, name), name) <= 0:
                raise CashCarryShadowError(f"{name} must be positive")
        if self.max_live_abs_basis_bps < self.max_entry_abs_basis_bps:
            raise CashCarryShadowError("live basis cap cannot be tighter than entry basis cap")
        if self.slippage_bps_per_fill >= 10_000.0:
            raise CashCarryShadowError("slippage must leave a positive simulated sell price")

    @property
    def config_sha256(self) -> str:
        return _sha256(dataclasses.asdict(self))

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any], *, enabled: Optional[bool] = None) -> "ShadowConfig":
        allowed = {field.name for field in dataclasses.fields(cls)}
        payload = {key: value for key, value in values.items() if key in allowed}
        if enabled is not None:
            payload["enabled"] = bool(enabled)
        return cls(**payload)


@dataclass(frozen=True)
class SimulatedFill:
    sequence: int
    leg: str
    action: str
    reference_side: str
    reference_price: float
    fill_price: float
    quantity: float
    notional_usd: float
    fee_bps: float
    fee_usd: float
    slippage_bps: float


@dataclass(frozen=True)
class FundingCashflow:
    settlement_id: str
    settled_at_ms: int
    rate: float
    perp_mark_price: float
    perp_notional_usd: float
    cashflow_usd: float
    side: str = "short_perp_receives_positive"


@dataclass
class _OpenCycle:
    cycle_id: str
    symbol: str
    opened_at_ms: int
    entry_observation_id: str
    target_notional_usd: float
    spot_qty: float
    perp_qty: float
    entry_spot_mid: float
    entry_perp_mid: float
    entry_basis_fraction: float
    entry_fills: tuple[SimulatedFill, SimulatedFill]
    funding_cashflows: list[FundingCashflow] = field(default_factory=list)
    max_abs_delta_drift_bps: float = 0.0


def _receipt_payload(receipt: "CycleReceipt") -> dict[str, Any]:
    payload = dataclasses.asdict(receipt)
    payload.pop("receipt_sha256", None)
    return payload


@dataclass(frozen=True)
class CycleReceipt:
    schema_id: str
    research_only: bool
    executable: bool
    broker_calls: bool
    performance_claims: bool
    source: str
    symbol: str
    cycle_id: str
    config_sha256: str
    entry_observation_id: str
    exit_observation_id: str
    opened_at_ms: int
    closed_at_ms: int
    close_reason: str
    target_notional_usd: float
    fills: tuple[SimulatedFill, ...]
    funding_cashflows: tuple[FundingCashflow, ...]
    entry_basis_bps: float
    exit_basis_bps: float
    adverse_basis_widen_bps: float
    max_abs_delta_drift_bps: float
    spot_leg_pnl_usd: float
    perp_leg_pnl_usd: float
    mark_to_market_gross_pnl_usd: float
    basis_change_pnl_usd: float
    residual_delta_pnl_usd: float
    execution_spread_slippage_cost_usd: float
    total_fee_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    receipt_sha256: str

    def verify(self) -> None:
        if self.schema_id != SCHEMA_ID:
            raise CashCarryShadowError("receipt schema mismatch")
        if not self.research_only or self.executable or self.broker_calls or self.performance_claims:
            raise CashCarryShadowError("receipt safety identity mismatch")
        if self.source != SOURCE_ID:
            raise CashCarryShadowError("receipt source mismatch")
        if self.close_reason not in {
            "funding_flip", "absolute_basis_guard", "adverse_basis_widen_guard",
            "delta_drift_guard", "max_hold_guard",
        }:
            raise CashCarryShadowError("receipt close reason is not canonical")
        expected_cycle_id = _sha256(
            {
                "schema_id": SCHEMA_ID,
                "symbol": self.symbol,
                "entry_observation_id": self.entry_observation_id,
                "config_sha256": self.config_sha256,
            }
        )
        if self.cycle_id != expected_cycle_id:
            raise CashCarryShadowError("cycle identity mismatch")
        if len(self.fills) != 4 or [fill.sequence for fill in self.fills] != [1, 2, 3, 4]:
            raise CashCarryShadowError("receipt must contain exactly four ordered fills")
        expected_roles = [
            ("spot", "buy", "ask"),
            ("linear_perp", "sell_short", "bid"),
            ("spot", "sell", "bid"),
            ("linear_perp", "buy_to_cover", "ask"),
        ]
        if [(x.leg, x.action, x.reference_side) for x in self.fills] != expected_roles:
            raise CashCarryShadowError("four-fill role contract mismatch")
        if self.closed_at_ms <= self.opened_at_ms:
            raise CashCarryShadowError("cycle must close strictly after entry")
        for fill in self.fills:
            for name in ("reference_price", "fill_price", "quantity", "notional_usd"):
                _positive(getattr(fill, name), f"fill {name}")
            if fill.fee_usd < 0 or fill.fee_bps < 0 or fill.slippage_bps < 0:
                raise CashCarryShadowError("negative execution cost")
            if not math.isclose(fill.notional_usd, fill.fill_price * fill.quantity, abs_tol=1e-8):
                raise CashCarryShadowError("fill notional does not reconcile")
            if not math.isclose(
                fill.fee_usd,
                fill.notional_usd * fill.fee_bps / 10_000.0,
                abs_tol=1e-8,
            ):
                raise CashCarryShadowError("fill fee does not reconcile")
        if not (
            self.fills[0].fill_price >= self.fills[0].reference_price
            and self.fills[1].fill_price <= self.fills[1].reference_price
            and self.fills[2].fill_price <= self.fills[2].reference_price
            and self.fills[3].fill_price >= self.fills[3].reference_price
        ):
            raise CashCarryShadowError("fill slippage is not adverse")
        if not math.isclose(self.fills[0].notional_usd, self.target_notional_usd, abs_tol=1e-8):
            raise CashCarryShadowError("spot entry is not equal target notional")
        if not math.isclose(self.fills[1].notional_usd, self.target_notional_usd, abs_tol=1e-8):
            raise CashCarryShadowError("perp entry is not equal target notional")
        expected_spot_pnl = (
            self.fills[2].fill_price - self.fills[0].fill_price
        ) * self.fills[0].quantity
        expected_perp_pnl = (
            self.fills[1].fill_price - self.fills[3].fill_price
        ) * self.fills[1].quantity
        if not math.isclose(self.spot_leg_pnl_usd, expected_spot_pnl, abs_tol=1e-8):
            raise CashCarryShadowError("spot leg P&L does not reconcile")
        if not math.isclose(self.perp_leg_pnl_usd, expected_perp_pnl, abs_tol=1e-8):
            raise CashCarryShadowError("perp leg P&L does not reconcile")
        if len({flow.settlement_id for flow in self.funding_cashflows}) != len(self.funding_cashflows):
            raise CashCarryShadowError("duplicate funding cashflow")
        for flow in self.funding_cashflows:
            if flow.settled_at_ms <= self.opened_at_ms or flow.settled_at_ms > self.closed_at_ms:
                raise CashCarryShadowError("funding cashflow is outside the open interval")
            if not math.isclose(
                flow.cashflow_usd,
                flow.perp_notional_usd * flow.rate,
                abs_tol=1e-8,
            ):
                raise CashCarryShadowError("funding cashflow does not reconcile")
        if not math.isclose(self.total_fee_usd, sum(x.fee_usd for x in self.fills), abs_tol=1e-8):
            raise CashCarryShadowError("total fees do not reconcile")
        if not math.isclose(
            self.funding_cashflow_usd,
            sum(x.cashflow_usd for x in self.funding_cashflows),
            abs_tol=1e-8,
        ):
            raise CashCarryShadowError("total funding does not reconcile")
        if self.execution_spread_slippage_cost_usd < -1e-8:
            raise CashCarryShadowError("adverse execution cost cannot be negative")
        expected_net = (
            self.spot_leg_pnl_usd
            + self.perp_leg_pnl_usd
            + self.funding_cashflow_usd
            - self.total_fee_usd
        )
        if not math.isclose(self.net_pnl_usd, expected_net, abs_tol=1e-8):
            raise CashCarryShadowError("receipt net P&L does not reconcile")
        if not math.isclose(
            self.mark_to_market_gross_pnl_usd,
            self.basis_change_pnl_usd + self.residual_delta_pnl_usd,
            abs_tol=1e-8,
        ):
            raise CashCarryShadowError("basis/delta decomposition does not reconcile")
        if self.receipt_sha256 != _sha256(_receipt_payload(self)):
            raise CashCarryShadowError("receipt checksum mismatch")

    def as_dict(self) -> dict[str, Any]:
        self.verify()
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class StepResult:
    action: str
    reason: str
    observation_id: str
    position_open: bool
    completed_positive_funding_count: int
    basis_bps: Optional[float] = None
    delta_drift_bps: Optional[float] = None
    receipt: Optional[CycleReceipt] = None


def _make_fill(
    *, sequence: int, leg: str, action: str, reference_side: str,
    reference_price: float, quantity: float, fee_bps: float,
    slippage_bps: float,
) -> SimulatedFill:
    slip = slippage_bps / 10_000.0
    is_buy = action in {"buy", "buy_to_cover"}
    fill_price = reference_price * (1.0 + slip if is_buy else 1.0 - slip)
    notional = quantity * fill_price
    fee = notional * fee_bps / 10_000.0
    return SimulatedFill(
        sequence=sequence,
        leg=leg,
        action=action,
        reference_side=reference_side,
        reference_price=_rounded(reference_price),
        fill_price=_rounded(fill_price),
        quantity=_rounded(quantity),
        notional_usd=_rounded(notional),
        fee_bps=_rounded(fee_bps),
        fee_usd=_rounded(fee),
        slippage_bps=_rounded(slippage_bps),
    )


class CashCarryShadowEngine:
    """Deterministic, in-memory state machine over public observations."""

    def __init__(self, config: Optional[ShadowConfig] = None) -> None:
        self.config = config or ShadowConfig()
        self._symbol: Optional[str] = None
        self._processed_observations: set[str] = set()
        self._processed_settlements: set[str] = set()
        self._settlement_rate_by_ts: dict[int, float] = {}
        self._positive_settlement_streak: list[FundingSettlement] = []
        self._position: Optional[_OpenCycle] = None

    @property
    def position_open(self) -> bool:
        return self._position is not None

    @property
    def positive_funding_count(self) -> int:
        return len(self._positive_settlement_streak)

    def _refuse(self, obs: PublicQuoteObservation, reason: str) -> StepResult:
        return StepResult(
            action="refuse",
            reason=reason,
            observation_id=obs.observation_id,
            position_open=self.position_open,
            completed_positive_funding_count=self.positive_funding_count,
        )

    def _validate_observation(self, obs: PublicQuoteObservation) -> Optional[str]:
        cfg = self.config
        if not obs.complete:
            return "incomplete_public_snapshot"
        if self._symbol is not None and obs.symbol != self._symbol:
            return "symbol_change_forbidden"
        if obs.spot_quote_ts_ms > obs.observed_at_ms or obs.perp_quote_ts_ms > obs.observed_at_ms:
            return "future_quote_timestamp"
        if obs.observed_at_ms - obs.spot_quote_ts_ms > cfg.max_quote_age_ms:
            return "stale_spot_quote"
        if obs.observed_at_ms - obs.perp_quote_ts_ms > cfg.max_quote_age_ms:
            return "stale_perp_quote"
        if abs(obs.spot_quote_ts_ms - obs.perp_quote_ts_ms) > cfg.max_quote_skew_ms:
            return "spot_perp_quote_skew"
        if self._position is not None:
            for funding in obs.funding_settlements:
                if (
                    funding.settlement_id not in self._processed_settlements
                    and funding.settled_at_ms > self._position.opened_at_ms
                ):
                    if funding.perp_mark_price is None:
                        return "missing_funding_settlement_price_proxy"
                    if obs.observed_at_ms - funding.settled_at_ms > cfg.max_funding_valuation_lag_ms:
                        return "late_funding_settlement_price_proxy"
        for funding in obs.funding_settlements:
            prior_rate = self._settlement_rate_by_ts.get(funding.settled_at_ms)
            if prior_rate is not None and not math.isclose(prior_rate, funding.rate, abs_tol=1e-15):
                return "funding_settlement_conflict"
        return None

    def _depth_ok_for_entry(self, obs: PublicQuoteObservation) -> bool:
        cfg = self.config
        slip = cfg.slippage_bps_per_fill / 10_000.0
        spot_fill = obs.spot_ask * (1.0 + slip)
        perp_fill = obs.perp_bid * (1.0 - slip)
        spot_qty = cfg.target_notional_usd / spot_fill
        perp_qty = cfg.target_notional_usd / perp_fill
        return spot_qty <= obs.spot_ask_qty and perp_qty <= obs.perp_bid_qty

    def _depth_ok_for_exit(self, obs: PublicQuoteObservation) -> bool:
        assert self._position is not None
        return (
            self._position.spot_qty <= obs.spot_bid_qty
            and self._position.perp_qty <= obs.perp_ask_qty
        )

    def _ingest_settlements(self, obs: PublicQuoteObservation) -> bool:
        pos = self._position
        settled_flip_observed = False
        for funding in obs.funding_settlements:
            if funding.settled_at_ms in self._settlement_rate_by_ts:
                continue
            if funding.settlement_id in self._processed_settlements:
                continue
            self._processed_settlements.add(funding.settlement_id)
            self._settlement_rate_by_ts[funding.settled_at_ms] = funding.rate
            if funding.rate >= self.config.min_entry_funding_rate:
                self._positive_settlement_streak.append(funding)
                keep = self.config.min_completed_funding_observations
                self._positive_settlement_streak = self._positive_settlement_streak[-keep:]
            else:
                self._positive_settlement_streak.clear()
                if funding.rate <= self.config.funding_flip_exit_rate:
                    settled_flip_observed = True

            if pos is not None and funding.settled_at_ms > pos.opened_at_ms:
                assert funding.perp_mark_price is not None  # guarded before mutation
                perp_notional = pos.perp_qty * funding.perp_mark_price
                cashflow = perp_notional * funding.rate  # short receives positive rate
                pos.funding_cashflows.append(
                    FundingCashflow(
                        settlement_id=funding.settlement_id,
                        settled_at_ms=funding.settled_at_ms,
                        rate=_rounded(funding.rate),
                        perp_mark_price=_rounded(funding.perp_mark_price),
                        perp_notional_usd=_rounded(perp_notional),
                        cashflow_usd=_rounded(cashflow),
                    )
                )

        # A published projected flip invalidates the old persistence sequence.
        if obs.projected_funding_rate <= self.config.funding_flip_exit_rate:
            self._positive_settlement_streak.clear()
        return settled_flip_observed

    def _open(self, obs: PublicQuoteObservation) -> StepResult:
        cfg = self.config
        slip = cfg.slippage_bps_per_fill / 10_000.0
        spot_fill_price = obs.spot_ask * (1.0 + slip)
        perp_fill_price = obs.perp_bid * (1.0 - slip)
        spot_qty = cfg.target_notional_usd / spot_fill_price
        perp_qty = cfg.target_notional_usd / perp_fill_price
        spot_fill = _make_fill(
            sequence=1, leg="spot", action="buy", reference_side="ask",
            reference_price=obs.spot_ask, quantity=spot_qty,
            fee_bps=cfg.spot_fee_bps, slippage_bps=cfg.slippage_bps_per_fill,
        )
        perp_fill = _make_fill(
            sequence=2, leg="linear_perp", action="sell_short", reference_side="bid",
            reference_price=obs.perp_bid, quantity=perp_qty,
            fee_bps=cfg.perp_fee_bps, slippage_bps=cfg.slippage_bps_per_fill,
        )
        cycle_id = _sha256(
            {
                "schema_id": SCHEMA_ID,
                "symbol": obs.symbol,
                "entry_observation_id": obs.observation_id,
                "config_sha256": cfg.config_sha256,
            }
        )
        self._position = _OpenCycle(
            cycle_id=cycle_id,
            symbol=obs.symbol,
            opened_at_ms=obs.observed_at_ms,
            entry_observation_id=obs.observation_id,
            target_notional_usd=cfg.target_notional_usd,
            spot_qty=spot_qty,
            perp_qty=perp_qty,
            entry_spot_mid=obs.spot_mid,
            entry_perp_mid=obs.perp_mid,
            entry_basis_fraction=obs.basis_fraction,
            entry_fills=(spot_fill, perp_fill),
        )
        return StepResult(
            action="open_shadow",
            reason="completed_funding_persistence_and_execution_guards_passed",
            observation_id=obs.observation_id,
            position_open=True,
            completed_positive_funding_count=self.positive_funding_count,
            basis_bps=_rounded(obs.basis_fraction * 10_000.0),
            delta_drift_bps=0.0,
        )

    def _metrics(self, obs: PublicQuoteObservation) -> tuple[float, float, float]:
        assert self._position is not None
        pos = self._position
        basis_bps = obs.basis_fraction * 10_000.0
        adverse_basis_bps = (obs.basis_fraction - pos.entry_basis_fraction) * 10_000.0
        delta_usd = pos.spot_qty * obs.spot_mid - pos.perp_qty * obs.perp_mid
        delta_bps = abs(delta_usd) / pos.target_notional_usd * 10_000.0
        pos.max_abs_delta_drift_bps = max(pos.max_abs_delta_drift_bps, delta_bps)
        return basis_bps, adverse_basis_bps, delta_bps

    def _close(self, obs: PublicQuoteObservation, reason: str) -> CycleReceipt:
        assert self._position is not None
        pos = self._position
        cfg = self.config
        exit_spot = _make_fill(
            sequence=3, leg="spot", action="sell", reference_side="bid",
            reference_price=obs.spot_bid, quantity=pos.spot_qty,
            fee_bps=cfg.spot_fee_bps, slippage_bps=cfg.slippage_bps_per_fill,
        )
        exit_perp = _make_fill(
            sequence=4, leg="linear_perp", action="buy_to_cover", reference_side="ask",
            reference_price=obs.perp_ask, quantity=pos.perp_qty,
            fee_bps=cfg.perp_fee_bps, slippage_bps=cfg.slippage_bps_per_fill,
        )
        fills: tuple[SimulatedFill, ...] = (*pos.entry_fills, exit_spot, exit_perp)
        entry_spot_fill, entry_perp_fill = pos.entry_fills
        spot_pnl = (exit_spot.fill_price - entry_spot_fill.fill_price) * pos.spot_qty
        perp_pnl = (entry_perp_fill.fill_price - exit_perp.fill_price) * pos.perp_qty

        mark_spot_pnl = (obs.spot_mid - pos.entry_spot_mid) * pos.spot_qty
        mark_perp_pnl = (pos.entry_perp_mid - obs.perp_mid) * pos.perp_qty
        mark_gross = mark_spot_pnl + mark_perp_pnl
        basis_change = pos.target_notional_usd * (pos.entry_basis_fraction - obs.basis_fraction)
        residual_delta = mark_gross - basis_change
        execution_cost = mark_gross - (spot_pnl + perp_pnl)
        fees = sum(x.fee_usd for x in fills)
        funding = sum(x.cashflow_usd for x in pos.funding_cashflows)
        net = spot_pnl + perp_pnl + funding - fees
        adverse_basis_bps = (obs.basis_fraction - pos.entry_basis_fraction) * 10_000.0

        values: dict[str, Any] = {
            "schema_id": SCHEMA_ID,
            "research_only": True,
            "executable": False,
            "broker_calls": False,
            "performance_claims": False,
            "source": SOURCE_ID,
            "symbol": pos.symbol,
            "cycle_id": pos.cycle_id,
            "config_sha256": cfg.config_sha256,
            "entry_observation_id": pos.entry_observation_id,
            "exit_observation_id": obs.observation_id,
            "opened_at_ms": pos.opened_at_ms,
            "closed_at_ms": obs.observed_at_ms,
            "close_reason": reason,
            "target_notional_usd": _rounded(pos.target_notional_usd),
            "fills": fills,
            "funding_cashflows": tuple(pos.funding_cashflows),
            "entry_basis_bps": _rounded(pos.entry_basis_fraction * 10_000.0),
            "exit_basis_bps": _rounded(obs.basis_fraction * 10_000.0),
            "adverse_basis_widen_bps": _rounded(adverse_basis_bps),
            "max_abs_delta_drift_bps": _rounded(pos.max_abs_delta_drift_bps),
            "spot_leg_pnl_usd": _rounded(spot_pnl),
            "perp_leg_pnl_usd": _rounded(perp_pnl),
            "mark_to_market_gross_pnl_usd": _rounded(mark_gross),
            "basis_change_pnl_usd": _rounded(basis_change),
            "residual_delta_pnl_usd": _rounded(residual_delta),
            "execution_spread_slippage_cost_usd": _rounded(execution_cost),
            "total_fee_usd": _rounded(fees),
            "funding_cashflow_usd": _rounded(funding),
            "net_pnl_usd": _rounded(net),
            "receipt_sha256": "",
        }
        probe = CycleReceipt(**values)
        receipt = dataclasses.replace(probe, receipt_sha256=_sha256(_receipt_payload(probe)))
        receipt.verify()
        self._position = None
        return receipt

    def step(self, obs: PublicQuoteObservation) -> StepResult:
        if not isinstance(obs, PublicQuoteObservation):
            raise CashCarryShadowError("step requires PublicQuoteObservation")
        if obs.observation_id in self._processed_observations:
            return StepResult(
                action="duplicate_noop",
                reason="observation_already_processed",
                observation_id=obs.observation_id,
                position_open=self.position_open,
                completed_positive_funding_count=self.positive_funding_count,
            )
        refusal = self._validate_observation(obs)
        if refusal:
            return self._refuse(obs, refusal)

        # Only valid, complete observations are marked processed.
        self._processed_observations.add(obs.observation_id)
        self._symbol = self._symbol or obs.symbol
        settled_flip_observed = self._ingest_settlements(obs)

        if not self.config.enabled:
            return StepResult(
                action="disabled_noop",
                reason="research_shadow_disabled_by_default",
                observation_id=obs.observation_id,
                position_open=self.position_open,
                completed_positive_funding_count=self.positive_funding_count,
                basis_bps=_rounded(obs.basis_fraction * 10_000.0),
            )

        if self._position is None:
            if self.positive_funding_count < self.config.min_completed_funding_observations:
                return StepResult(
                    action="observe",
                    reason="completed_funding_persistence_not_met",
                    observation_id=obs.observation_id,
                    position_open=False,
                    completed_positive_funding_count=self.positive_funding_count,
                    basis_bps=_rounded(obs.basis_fraction * 10_000.0),
                )
            if (
                obs.observed_at_ms - self._positive_settlement_streak[-1].settled_at_ms
                > self.config.max_latest_completed_funding_age_ms
            ):
                return StepResult(
                    action="observe",
                    reason="latest_completed_funding_is_stale",
                    observation_id=obs.observation_id,
                    position_open=False,
                    completed_positive_funding_count=self.positive_funding_count,
                    basis_bps=_rounded(obs.basis_fraction * 10_000.0),
                )
            if (
                self._positive_settlement_streak[-1].settled_at_ms
                - self._positive_settlement_streak[0].settled_at_ms
                > self.config.max_funding_persistence_span_ms
            ):
                return StepResult(
                    action="observe",
                    reason="completed_funding_persistence_is_too_sparse",
                    observation_id=obs.observation_id,
                    position_open=False,
                    completed_positive_funding_count=self.positive_funding_count,
                    basis_bps=_rounded(obs.basis_fraction * 10_000.0),
                )
            if obs.projected_funding_rate < self.config.min_entry_funding_rate:
                return StepResult(
                    action="observe",
                    reason="projected_funding_below_entry_minimum",
                    observation_id=obs.observation_id,
                    position_open=False,
                    completed_positive_funding_count=self.positive_funding_count,
                    basis_bps=_rounded(obs.basis_fraction * 10_000.0),
                )
            if abs(obs.basis_fraction * 10_000.0) > self.config.max_entry_abs_basis_bps:
                return StepResult(
                    action="observe",
                    reason="entry_basis_guard",
                    observation_id=obs.observation_id,
                    position_open=False,
                    completed_positive_funding_count=self.positive_funding_count,
                    basis_bps=_rounded(obs.basis_fraction * 10_000.0),
                )
            if not self._depth_ok_for_entry(obs):
                return self._refuse(obs, "entry_top_of_book_depth_insufficient_partial_fill_forbidden")
            return self._open(obs)

        basis_bps, adverse_basis_bps, delta_bps = self._metrics(obs)
        reason = ""
        if settled_flip_observed or obs.projected_funding_rate <= self.config.funding_flip_exit_rate:
            reason = "funding_flip"
        elif abs(basis_bps) > self.config.max_live_abs_basis_bps:
            reason = "absolute_basis_guard"
        elif adverse_basis_bps > self.config.max_adverse_basis_widen_bps:
            reason = "adverse_basis_widen_guard"
        elif delta_bps > self.config.max_delta_drift_bps:
            reason = "delta_drift_guard"
        elif obs.observed_at_ms - self._position.opened_at_ms >= self.config.max_hold_ms:
            reason = "max_hold_guard"

        if reason:
            if not self._depth_ok_for_exit(obs):
                return self._refuse(obs, "exit_top_of_book_depth_insufficient_partial_fill_forbidden")
            receipt = self._close(obs, reason)
            return StepResult(
                action="close_shadow",
                reason=reason,
                observation_id=obs.observation_id,
                position_open=False,
                completed_positive_funding_count=self.positive_funding_count,
                basis_bps=_rounded(basis_bps),
                delta_drift_bps=_rounded(delta_bps),
                receipt=receipt,
            )

        return StepResult(
            action="hold_shadow",
            reason="neutral_carry_guards_passed",
            observation_id=obs.observation_id,
            position_open=True,
            completed_positive_funding_count=self.positive_funding_count,
            basis_bps=_rounded(basis_bps),
            delta_drift_bps=_rounded(delta_bps),
        )


def replay_observations(
    observations: Iterable[PublicQuoteObservation],
    config: ShadowConfig,
) -> tuple[list[StepResult], list[CycleReceipt]]:
    engine = CashCarryShadowEngine(config)
    steps: list[StepResult] = []
    receipts: list[CycleReceipt] = []
    for obs in observations:
        result = engine.step(obs)
        steps.append(result)
        if result.receipt is not None:
            receipts.append(result.receipt)
    return steps, receipts


def append_cycle_receipt(path: Path | str, receipt: CycleReceipt) -> bool:
    """Append one immutable receipt; identical replay is a no-op.

    Returns ``True`` for a new append and ``False`` when the exact cycle receipt
    already exists.  A cycle-id collision with different content or any corrupt
    existing line fails closed.
    """

    receipt.verify()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and stat.S_ISLNK(target.lstat().st_mode):
        raise CashCarryShadowError("receipt ledger symlink is forbidden")
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.lseek(fd, 0, os.SEEK_SET)
        existing = os.read(fd, max(1, os.fstat(fd).st_size)).decode("utf-8")
        for line_no, line in enumerate(existing.splitlines(), start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CashCarryShadowError(f"corrupt receipt ledger line {line_no}") from exc
            if row.get("cycle_id") == receipt.cycle_id:
                if row.get("receipt_sha256") == receipt.receipt_sha256:
                    return False
                raise CashCarryShadowError("cycle-id collision with different receipt")
        data = _canonical(receipt.as_dict()) + b"\n"
        written = os.write(fd, data)
        if written != len(data):
            raise CashCarryShadowError("short append to receipt ledger")
        os.fsync(fd)
        return True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def observations_from_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[PublicQuoteObservation]:
    rows: Sequence[Mapping[str, Any]]
    if isinstance(payload, Mapping):
        rows = payload.get("observations") or []
    else:
        rows = payload
    return [PublicQuoteObservation.from_mapping(row) for row in rows]


__all__ = [
    "CashCarryShadowEngine",
    "CashCarryShadowError",
    "CycleReceipt",
    "FundingCashflow",
    "FundingSettlement",
    "PublicQuoteObservation",
    "SCHEMA_ID",
    "SOURCE_ID",
    "ShadowConfig",
    "SimulatedFill",
    "StepResult",
    "append_cycle_receipt",
    "observations_from_json",
    "replay_observations",
]
