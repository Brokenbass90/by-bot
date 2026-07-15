"""Durable research-only public collector for Bybit cash-and-carry v1.

This module is an event-sourced *paper mechanics* layer around the frozen v1
shadow engine.  It deliberately contains no HTTP client, authentication,
environment reads, private endpoints, order endpoints, or execution authority.

V2 adds the pieces that a restartable public paper collector needs:

* exact public instrument receipts (tick, quantity step, minima, funding interval);
* deterministic full-depth book walks with common-base-quantity quantization;
* a conservative break-even gate before a v1 paper cycle may open;
* one checksummed append-only journal record containing the observation, decision,
  and post-step open-cycle state;
* deterministic replay/recovery and duplicate-observation idempotency.

The v1 engine remains unchanged and its receipt is still mechanics evidence, not
an executable order plan or a performance claim.  The quantized v2 plan is stored
alongside it so the remaining parity gap is explicit rather than hidden.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import math
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

from bot.bybit_cashcarry_shadow_v1 import (
    CashCarryShadowEngine,
    CashCarryShadowError,
    FundingSettlement,
    PublicQuoteObservation,
    ShadowConfig,
)


SNAPSHOT_SCHEMA_ID = "bybit_public_cashcarry_snapshot_v2"
JOURNAL_SCHEMA_ID = "bybit_cashcarry_durable_journal_record_v2"
STATE_SCHEMA_ID = "bybit_cashcarry_open_state_v2"
PLAN_SCHEMA_ID = "bybit_cashcarry_quantized_book_plan_v2"
SOURCE_ID = "bybit_public_v5"


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


def _decimal(value: Any, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise CashCarryShadowError(f"{name} must be decimal")
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CashCarryShadowError(f"{name} must be decimal") from exc
    if not out.is_finite():
        raise CashCarryShadowError(f"{name} must be finite")
    if positive and out <= 0:
        raise CashCarryShadowError(f"{name} must be positive")
    return out


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    return "0" if text in {"-0", ""} else text


def _exact_ms(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CashCarryShadowError(f"{name} must be an integer timestamp")
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise CashCarryShadowError(f"{name} must be an integer timestamp") from exc
    if out < 0 or Decimal(str(value)) != Decimal(out):
        raise CashCarryShadowError(f"{name} must be a non-negative exact integer")
    return out


def _is_step_aligned(value: Decimal, step: Decimal) -> bool:
    return value % step == 0


def _floor_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _common_step(first: Decimal, second: Decimal) -> Decimal:
    places = max(max(0, -first.as_tuple().exponent), max(0, -second.as_tuple().exponent))
    scale = 10**places
    left = int(first * scale)
    right = int(second * scale)
    common = abs(left * right) // math.gcd(left, right)
    return Decimal(common) / Decimal(scale)


@dataclass(frozen=True)
class InstrumentLegRules:
    market: str
    tick_size: str
    qty_step: str
    min_order_qty: str
    min_notional_usd: str

    def __post_init__(self) -> None:
        if self.market not in {"spot", "linear_perp"}:
            raise CashCarryShadowError("instrument market must be spot or linear_perp")
        for name in ("tick_size", "qty_step", "min_order_qty", "min_notional_usd"):
            value = _decimal(getattr(self, name), name, positive=True)
            object.__setattr__(self, name, _decimal_text(value))
        if not _is_step_aligned(self.min_order_qty_decimal, self.qty_step_decimal):
            raise CashCarryShadowError(f"{self.market} minimum quantity is not qty-step aligned")

    @property
    def tick_size_decimal(self) -> Decimal:
        return Decimal(self.tick_size)

    @property
    def qty_step_decimal(self) -> Decimal:
        return Decimal(self.qty_step)

    @property
    def min_order_qty_decimal(self) -> Decimal:
        return Decimal(self.min_order_qty)

    @property
    def min_notional_decimal(self) -> Decimal:
        return Decimal(self.min_notional_usd)


@dataclass(frozen=True)
class InstrumentRulesV2:
    symbol: str
    funding_interval_minutes: int
    spot: InstrumentLegRules
    linear_perp: InstrumentLegRules

    def __post_init__(self) -> None:
        symbol = str(self.symbol).strip().upper()
        if not symbol.endswith("USDT"):
            raise CashCarryShadowError("instrument symbol must be an explicit USDT market")
        object.__setattr__(self, "symbol", symbol)
        if isinstance(self.funding_interval_minutes, bool):
            raise CashCarryShadowError("funding interval must be an integer")
        interval = int(self.funding_interval_minutes)
        if interval <= 0 or float(self.funding_interval_minutes) != float(interval):
            raise CashCarryShadowError("funding interval must be a positive exact integer")
        object.__setattr__(self, "funding_interval_minutes", interval)
        if self.spot.market != "spot" or self.linear_perp.market != "linear_perp":
            raise CashCarryShadowError("instrument leg rules are assigned to the wrong market")

    @property
    def common_qty_step(self) -> Decimal:
        return _common_step(self.spot.qty_step_decimal, self.linear_perp.qty_step_decimal)

    def payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "InstrumentRulesV2":
        return cls(
            symbol=row["symbol"],
            funding_interval_minutes=row["funding_interval_minutes"],
            spot=InstrumentLegRules(**row["spot"]),
            linear_perp=InstrumentLegRules(**row["linear_perp"]),
        )


@dataclass(frozen=True)
class BookLevel:
    price: str
    quantity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _decimal_text(_decimal(self.price, "book price", positive=True)))
        object.__setattr__(self, "quantity", _decimal_text(_decimal(self.quantity, "book quantity", positive=True)))

    @property
    def price_decimal(self) -> Decimal:
        return Decimal(self.price)

    @property
    def quantity_decimal(self) -> Decimal:
        return Decimal(self.quantity)

    @classmethod
    def from_sequence(cls, row: Sequence[Any]) -> "BookLevel":
        if len(row) < 2:
            raise CashCarryShadowError("book level must contain price and quantity")
        return cls(price=str(row[0]), quantity=str(row[1]))


def _validate_book(
    bids: tuple[BookLevel, ...],
    asks: tuple[BookLevel, ...],
    rules: InstrumentLegRules,
    label: str,
) -> None:
    if not bids or not asks:
        raise CashCarryShadowError(f"{label} book must have both sides")
    bid_prices = [row.price_decimal for row in bids]
    ask_prices = [row.price_decimal for row in asks]
    if bid_prices != sorted(bid_prices, reverse=True) or len(set(bid_prices)) != len(bid_prices):
        raise CashCarryShadowError(f"{label} bids must be unique and descending")
    if ask_prices != sorted(ask_prices) or len(set(ask_prices)) != len(ask_prices):
        raise CashCarryShadowError(f"{label} asks must be unique and ascending")
    if bid_prices[0] > ask_prices[0]:
        raise CashCarryShadowError(f"{label} book is crossed")
    for row in (*bids, *asks):
        if not _is_step_aligned(row.price_decimal, rules.tick_size_decimal):
            raise CashCarryShadowError(f"{label} price is not tick-size aligned")


@dataclass(frozen=True)
class PublicMarketSnapshotV2:
    symbol: str
    observed_at_ms: int
    spot_book_ts_ms: int
    perp_book_ts_ms: int
    spot_bids: tuple[BookLevel, ...]
    spot_asks: tuple[BookLevel, ...]
    perp_bids: tuple[BookLevel, ...]
    perp_asks: tuple[BookLevel, ...]
    projected_funding_rate: float
    next_funding_time_ms: int
    funding_settlements: tuple[FundingSettlement, ...]
    instruments: InstrumentRulesV2
    complete: bool = True
    source: str = SOURCE_ID

    def __post_init__(self) -> None:
        symbol = str(self.symbol).strip().upper()
        if symbol != self.instruments.symbol:
            raise CashCarryShadowError("snapshot/instrument symbol mismatch")
        object.__setattr__(self, "symbol", symbol)
        for name in ("observed_at_ms", "spot_book_ts_ms", "perp_book_ts_ms", "next_funding_time_ms"):
            _exact_ms(getattr(self, name), name)
        if self.spot_book_ts_ms > self.observed_at_ms or self.perp_book_ts_ms > self.observed_at_ms:
            raise CashCarryShadowError("future book timestamp is forbidden")
        if self.next_funding_time_ms <= self.observed_at_ms:
            raise CashCarryShadowError("next funding time must be in the future")
        rate = float(self.projected_funding_rate)
        if not math.isfinite(rate):
            raise CashCarryShadowError("projected funding must be finite")
        object.__setattr__(self, "projected_funding_rate", rate)
        if not isinstance(self.complete, bool):
            raise CashCarryShadowError("complete must be boolean")
        if self.source != SOURCE_ID:
            raise CashCarryShadowError("only the frozen public Bybit source is accepted")
        for name in ("spot_bids", "spot_asks", "perp_bids", "perp_asks"):
            levels = tuple(getattr(self, name))
            if any(not isinstance(level, BookLevel) for level in levels):
                raise CashCarryShadowError(f"{name} must contain BookLevel")
            object.__setattr__(self, name, levels)
        _validate_book(self.spot_bids, self.spot_asks, self.instruments.spot, "spot")
        _validate_book(self.perp_bids, self.perp_asks, self.instruments.linear_perp, "perp")
        settlements = tuple(self.funding_settlements)
        if list(settlements) != sorted(settlements, key=lambda item: item.settled_at_ms):
            raise CashCarryShadowError("funding settlements must be timestamp sorted")
        if len({item.settlement_id for item in settlements}) != len(settlements):
            raise CashCarryShadowError("duplicate funding settlement")
        if any(item.settled_at_ms > self.observed_at_ms for item in settlements):
            raise CashCarryShadowError("future funding settlement is forbidden")
        object.__setattr__(self, "funding_settlements", settlements)

    @property
    def spot_mid(self) -> Decimal:
        return (self.spot_bids[0].price_decimal + self.spot_asks[0].price_decimal) / Decimal(2)

    @property
    def perp_mid(self) -> Decimal:
        return (self.perp_bids[0].price_decimal + self.perp_asks[0].price_decimal) / Decimal(2)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_id": SNAPSHOT_SCHEMA_ID,
            "source": self.source,
            "symbol": self.symbol,
            "observed_at_ms": self.observed_at_ms,
            "spot_book_ts_ms": self.spot_book_ts_ms,
            "perp_book_ts_ms": self.perp_book_ts_ms,
            "spot_bids": [dataclasses.asdict(level) for level in self.spot_bids],
            "spot_asks": [dataclasses.asdict(level) for level in self.spot_asks],
            "perp_bids": [dataclasses.asdict(level) for level in self.perp_bids],
            "perp_asks": [dataclasses.asdict(level) for level in self.perp_asks],
            "projected_funding_rate": self.projected_funding_rate,
            "next_funding_time_ms": self.next_funding_time_ms,
            "funding_settlements": [dataclasses.asdict(item) for item in self.funding_settlements],
            "instruments": self.instruments.payload(),
            "complete": self.complete,
        }

    @property
    def observation_id(self) -> str:
        return _sha256(self.payload())

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "PublicMarketSnapshotV2":
        def levels(name: str) -> tuple[BookLevel, ...]:
            return tuple(
                BookLevel(**item) if isinstance(item, Mapping) else BookLevel.from_sequence(item)
                for item in row[name]
            )

        return cls(
            symbol=row["symbol"],
            observed_at_ms=row["observed_at_ms"],
            spot_book_ts_ms=row["spot_book_ts_ms"],
            perp_book_ts_ms=row["perp_book_ts_ms"],
            spot_bids=levels("spot_bids"),
            spot_asks=levels("spot_asks"),
            perp_bids=levels("perp_bids"),
            perp_asks=levels("perp_asks"),
            projected_funding_rate=row["projected_funding_rate"],
            next_funding_time_ms=row["next_funding_time_ms"],
            funding_settlements=tuple(
                FundingSettlement(
                    settled_at_ms=item["settled_at_ms"],
                    rate=item["rate"],
                    perp_mark_price=item.get("perp_mark_price"),
                )
                for item in row.get("funding_settlements", [])
            ),
            instruments=InstrumentRulesV2.from_mapping(row["instruments"]),
            complete=row.get("complete", True),
            source=row.get("source", SOURCE_ID),
        )


@dataclass(frozen=True)
class WalkSlice:
    price: str
    quantity: str
    notional_usd: str


@dataclass(frozen=True)
class BookWalk:
    market: str
    action: str
    quantity: str
    raw_vwap: str
    adverse_fill_price: str
    limit_guard_price: str
    notional_usd: str
    levels_consumed: int
    slices: tuple[WalkSlice, ...]


@dataclass(frozen=True)
class QuantizedExecutionPlanV2:
    schema_id: str
    phase: str
    symbol: str
    common_qty_step: str
    quantity: str
    spot: BookWalk
    linear_perp: BookWalk
    full_fill_only: bool
    partial_fill_recovery: str
    plan_sha256: str

    def payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _walk(
    levels: Sequence[BookLevel],
    quantity: Decimal,
    *,
    market: str,
    action: str,
    tick_size: Decimal,
    slippage_bps: Decimal,
) -> BookWalk:
    remaining = quantity
    gross = Decimal(0)
    slices: list[WalkSlice] = []
    for level in levels:
        take = min(remaining, level.quantity_decimal)
        if take <= 0:
            continue
        notional = take * level.price_decimal
        slices.append(
            WalkSlice(
                price=level.price,
                quantity=_decimal_text(take),
                notional_usd=_decimal_text(notional),
            )
        )
        gross += notional
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0:
        raise CashCarryShadowError(
            f"{market} {action} depth insufficient; partial fills are forbidden"
        )
    raw_vwap = gross / quantity
    adverse = slippage_bps / Decimal(10_000)
    is_buy = action in {"buy", "buy_to_cover"}
    fill_price = raw_vwap * (Decimal(1) + adverse if is_buy else Decimal(1) - adverse)
    worst = slices[-1]
    worst_price = Decimal(worst.price)
    raw_guard = worst_price * (Decimal(1) + adverse if is_buy else Decimal(1) - adverse)
    guard = _ceil_step(raw_guard, tick_size) if is_buy else _floor_step(raw_guard, tick_size)
    return BookWalk(
        market=market,
        action=action,
        quantity=_decimal_text(quantity),
        raw_vwap=_decimal_text(raw_vwap),
        adverse_fill_price=_decimal_text(fill_price),
        limit_guard_price=_decimal_text(guard),
        notional_usd=_decimal_text(fill_price * quantity),
        levels_consumed=len(slices),
        slices=tuple(slices),
    )


def build_quantized_execution_plan(
    snapshot: PublicMarketSnapshotV2,
    *,
    target_notional_usd: float,
    slippage_bps_per_fill: float,
    phase: str = "entry",
    quantity: Optional[str] = None,
) -> QuantizedExecutionPlanV2:
    """Build a deterministic all-or-none two-leg paper execution plan."""

    if phase not in {"entry", "exit"}:
        raise CashCarryShadowError("plan phase must be entry or exit")
    target = _decimal(target_notional_usd, "target notional", positive=True)
    slippage = _decimal(slippage_bps_per_fill, "slippage bps")
    if slippage < 0 or slippage >= 10_000:
        raise CashCarryShadowError("slippage bps are outside the safe range")
    common = snapshot.instruments.common_qty_step
    if quantity is None:
        raw_qty = min(
            target / snapshot.spot_asks[0].price_decimal,
            target / snapshot.perp_bids[0].price_decimal,
        )
        qty = _floor_step(raw_qty, common)
    else:
        qty = _decimal(quantity, "exit quantity", positive=True)
        if not _is_step_aligned(qty, common):
            raise CashCarryShadowError("exit quantity is not aligned to the common quantity grid")
    minimum_qty = max(
        snapshot.instruments.spot.min_order_qty_decimal,
        snapshot.instruments.linear_perp.min_order_qty_decimal,
    )
    if qty < minimum_qty or qty <= 0:
        raise CashCarryShadowError("common quantity is below an instrument minimum")

    if phase == "entry":
        spot_levels, spot_action = snapshot.spot_asks, "buy"
        perp_levels, perp_action = snapshot.perp_bids, "sell_short"
    else:
        spot_levels, spot_action = snapshot.spot_bids, "sell"
        perp_levels, perp_action = snapshot.perp_asks, "buy_to_cover"
    spot = _walk(
        spot_levels,
        qty,
        market="spot",
        action=spot_action,
        tick_size=snapshot.instruments.spot.tick_size_decimal,
        slippage_bps=slippage,
    )
    perp = _walk(
        perp_levels,
        qty,
        market="linear_perp",
        action=perp_action,
        tick_size=snapshot.instruments.linear_perp.tick_size_decimal,
        slippage_bps=slippage,
    )
    if Decimal(spot.notional_usd) < snapshot.instruments.spot.min_notional_decimal:
        raise CashCarryShadowError("spot walked notional is below minimum")
    if Decimal(perp.notional_usd) < snapshot.instruments.linear_perp.min_notional_decimal:
        raise CashCarryShadowError("perp walked notional is below minimum")
    core = {
        "schema_id": PLAN_SCHEMA_ID,
        "phase": phase,
        "symbol": snapshot.symbol,
        "common_qty_step": _decimal_text(common),
        "quantity": _decimal_text(qty),
        "spot": dataclasses.asdict(spot),
        "linear_perp": dataclasses.asdict(perp),
        "full_fill_only": True,
        "partial_fill_recovery": "REFUSE_BEFORE_STATE_MUTATION",
    }
    return QuantizedExecutionPlanV2(
        schema_id=PLAN_SCHEMA_ID,
        phase=phase,
        symbol=snapshot.symbol,
        common_qty_step=_decimal_text(common),
        quantity=_decimal_text(qty),
        spot=spot,
        linear_perp=perp,
        full_fill_only=True,
        partial_fill_recovery="REFUSE_BEFORE_STATE_MUTATION",
        plan_sha256=_sha256(core),
    )


@dataclass(frozen=True)
class BreakEvenGateV2:
    passed: bool
    reason: str
    conservative_funding_rate: float
    expected_settlements_before_max_hold: int
    expected_carry_bps: float
    walked_round_trip_execution_bps: float
    four_fill_fee_bps: float
    basis_stress_bps: float
    minimum_edge_bps: float
    required_carry_bps: float


@dataclass(frozen=True)
class DurableCollectorConfigV2:
    enabled: bool = False
    shadow_enabled: bool = False
    basis_stress_bps: float = 10.0
    minimum_expected_edge_bps: float = 5.0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool) or not isinstance(self.shadow_enabled, bool):
            raise CashCarryShadowError("collector/shadow enabled flags must be boolean")
        if self.shadow_enabled and not self.enabled:
            raise CashCarryShadowError("shadow cannot be enabled while durable collector is disabled")
        for name in ("basis_stress_bps", "minimum_expected_edge_bps"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise CashCarryShadowError(f"{name} must be non-negative and finite")

    @property
    def config_sha256(self) -> str:
        return _sha256(dataclasses.asdict(self))


def break_even_gate(
    snapshot: PublicMarketSnapshotV2,
    plan: QuantizedExecutionPlanV2,
    shadow_config: ShadowConfig,
    collector_config: DurableCollectorConfigV2,
) -> BreakEvenGateV2:
    completed = [
        item.rate
        for item in snapshot.funding_settlements[-shadow_config.min_completed_funding_observations :]
    ]
    if len(completed) < shadow_config.min_completed_funding_observations:
        conservative_rate = min([snapshot.projected_funding_rate, *completed]) if completed else snapshot.projected_funding_rate
    else:
        conservative_rate = min(snapshot.projected_funding_rate, *completed)
    interval_ms = snapshot.instruments.funding_interval_minutes * 60_000
    settlements = max(0, int(shadow_config.max_hold_ms // interval_ms))
    carry_bps = max(0.0, conservative_rate) * settlements * 10_000.0
    spot_mid = float(snapshot.spot_mid)
    perp_mid = float(snapshot.perp_mid)
    spot_fill = float(plan.spot.adverse_fill_price)
    perp_fill = float(plan.linear_perp.adverse_fill_price)
    # Assume the same public spread/depth cost at exit.  No basis convergence
    # profit is credited; an independent adverse basis reserve is added below.
    execution_bps = max(0.0, (spot_fill / spot_mid - 1.0) * 10_000.0) * 2.0
    execution_bps += max(0.0, (1.0 - perp_fill / perp_mid) * 10_000.0) * 2.0
    fee_bps = 2.0 * shadow_config.spot_fee_bps + 2.0 * shadow_config.perp_fee_bps
    required = (
        execution_bps
        + fee_bps
        + collector_config.basis_stress_bps
        + collector_config.minimum_expected_edge_bps
    )
    persistence_ok = len(completed) >= shadow_config.min_completed_funding_observations
    passed = (
        persistence_ok
        and conservative_rate >= shadow_config.min_entry_funding_rate
        and carry_bps >= required
    )
    if not persistence_ok:
        reason = "completed_funding_persistence_not_met"
    elif conservative_rate < shadow_config.min_entry_funding_rate:
        reason = "conservative_funding_below_entry_minimum"
    elif carry_bps < required:
        reason = "expected_carry_does_not_cover_four_fills_and_basis_stress"
    else:
        reason = "conservative_break_even_gate_passed"
    return BreakEvenGateV2(
        passed=passed,
        reason=reason,
        conservative_funding_rate=round(float(conservative_rate), 12),
        expected_settlements_before_max_hold=settlements,
        expected_carry_bps=round(carry_bps, 9),
        walked_round_trip_execution_bps=round(execution_bps, 9),
        four_fill_fee_bps=round(fee_bps, 9),
        basis_stress_bps=round(collector_config.basis_stress_bps, 9),
        minimum_edge_bps=round(collector_config.minimum_expected_edge_bps, 9),
        required_carry_bps=round(required, 9),
    )


def _step_payload(step: Any) -> dict[str, Any]:
    return dataclasses.asdict(step)


def _legacy_open_state(engine: CashCarryShadowEngine) -> Optional[dict[str, Any]]:
    position = getattr(engine, "_position", None)
    return dataclasses.asdict(position) if position is not None else None


def _state_payload(
    engine: CashCarryShadowEngine,
    active_plan: Optional[QuantizedExecutionPlanV2],
) -> dict[str, Any]:
    core = {
        "schema_id": STATE_SCHEMA_ID,
        "position_open": engine.position_open,
        "positive_funding_count": engine.positive_funding_count,
        "legacy_v1_open_cycle": _legacy_open_state(engine),
        "quantized_open_plan": active_plan.payload() if active_plan is not None else None,
        "processed_observation_count": len(getattr(engine, "_processed_observations", set())),
        "processed_settlement_count": len(getattr(engine, "_processed_settlements", set())),
    }
    core["state_sha256"] = _sha256(core)
    return core


@dataclass
class _Recovered:
    engine: CashCarryShadowEngine
    active_plan: Optional[QuantizedExecutionPlanV2]
    records: list[dict[str, Any]]


class DurableCashCarryJournalV2:
    """Single-writer, append-only observation plus open-state journal."""

    def __init__(
        self,
        path: Path | str,
        *,
        shadow_config: Optional[ShadowConfig] = None,
        collector_config: Optional[DurableCollectorConfigV2] = None,
    ) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.collector_config = collector_config or DurableCollectorConfigV2()
        base = shadow_config or ShadowConfig()
        self.shadow_config = dataclasses.replace(
            base,
            enabled=self.collector_config.shadow_enabled,
        )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for target, label in ((self.path, "journal"), (self.lock_path, "journal lock")):
            if target.exists() and stat.S_ISLNK(target.lstat().st_mode):
                raise CashCarryShadowError(f"{label} symlink is forbidden")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.lock_path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise CashCarryShadowError("torn journal tail")
        rows: list[dict[str, Any]] = []
        previous = "0" * 64
        for sequence, line in enumerate(raw.splitlines(), start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CashCarryShadowError(f"corrupt journal line {sequence}") from exc
            if row.get("schema_id") != JOURNAL_SCHEMA_ID or row.get("sequence") != sequence:
                raise CashCarryShadowError(f"journal sequence/schema mismatch at line {sequence}")
            if row.get("previous_record_sha256") != previous:
                raise CashCarryShadowError(f"journal hash-chain mismatch at line {sequence}")
            supplied = row.get("record_sha256")
            core = dict(row)
            core.pop("record_sha256", None)
            if supplied != _sha256(core):
                raise CashCarryShadowError(f"journal checksum mismatch at line {sequence}")
            if row.get("collector_config_sha256") != self.collector_config.config_sha256:
                raise CashCarryShadowError("journal collector config differs from replay config")
            if row.get("shadow_config_sha256") != self.shadow_config.config_sha256:
                raise CashCarryShadowError("journal shadow config differs from replay config")
            rows.append(row)
            previous = supplied
        return rows

    def _effective_observation(
        self,
        snapshot: PublicMarketSnapshotV2,
        plan: Optional[QuantizedExecutionPlanV2],
        *,
        economics_passed: bool,
        position_open: bool,
    ) -> PublicQuoteObservation:
        spot_bid = float(snapshot.spot_bids[0].price)
        spot_ask = float(snapshot.spot_asks[0].price)
        perp_bid = float(snapshot.perp_bids[0].price)
        perp_ask = float(snapshot.perp_asks[0].price)
        depth = 1e-18
        if plan is not None:
            depth = max(float(plan.quantity) * 100.0, 1.0)
            if plan.phase == "entry":
                spot_ask = float(plan.spot.raw_vwap)
                perp_bid = float(plan.linear_perp.raw_vwap)
            else:
                spot_bid = float(plan.spot.raw_vwap)
                perp_ask = float(plan.linear_perp.raw_vwap)
        projected = snapshot.projected_funding_rate
        if not position_open and not economics_passed and projected >= self.shadow_config.min_entry_funding_rate:
            # Preserve the completed-funding streak while keeping the frozen v1
            # entry gate closed.  A positive sub-threshold projection does not
            # clear v1 persistence, unlike a fabricated zero/negative value.
            projected = max(
                self.shadow_config.funding_flip_exit_rate + 1e-15,
                self.shadow_config.min_entry_funding_rate / 2.0,
            )
        return PublicQuoteObservation(
            symbol=snapshot.symbol,
            observed_at_ms=snapshot.observed_at_ms,
            spot_quote_ts_ms=snapshot.spot_book_ts_ms,
            perp_quote_ts_ms=snapshot.perp_book_ts_ms,
            spot_bid=spot_bid,
            spot_ask=spot_ask,
            spot_bid_qty=depth,
            spot_ask_qty=depth,
            perp_bid=perp_bid,
            perp_ask=perp_ask,
            perp_bid_qty=depth,
            perp_ask_qty=depth,
            projected_funding_rate=projected,
            next_funding_time_ms=snapshot.next_funding_time_ms,
            funding_settlements=snapshot.funding_settlements,
            complete=snapshot.complete,
            source=snapshot.source,
        )

    def _transition(
        self,
        engine: CashCarryShadowEngine,
        active_plan: Optional[QuantizedExecutionPlanV2],
        snapshot: PublicMarketSnapshotV2,
    ) -> tuple[dict[str, Any], Optional[QuantizedExecutionPlanV2]]:
        plan: Optional[QuantizedExecutionPlanV2] = None
        plan_error: Optional[str] = None
        economics: Optional[BreakEvenGateV2] = None
        was_open = engine.position_open
        try:
            if was_open:
                if active_plan is None:
                    raise CashCarryShadowError("open legacy cycle is missing its quantized v2 plan")
                plan = build_quantized_execution_plan(
                    snapshot,
                    target_notional_usd=self.shadow_config.target_notional_usd,
                    slippage_bps_per_fill=self.shadow_config.slippage_bps_per_fill,
                    phase="exit",
                    quantity=active_plan.quantity,
                )
            else:
                plan = build_quantized_execution_plan(
                    snapshot,
                    target_notional_usd=self.shadow_config.target_notional_usd,
                    slippage_bps_per_fill=self.shadow_config.slippage_bps_per_fill,
                    phase="entry",
                )
                economics = break_even_gate(
                    snapshot,
                    plan,
                    self.shadow_config,
                    self.collector_config,
                )
        except CashCarryShadowError as exc:
            plan_error = str(exc)

        economics_passed = bool(economics and economics.passed)
        effective = self._effective_observation(
            snapshot,
            plan,
            economics_passed=economics_passed,
            position_open=was_open,
        )
        step = engine.step(effective)
        next_active = active_plan
        if step.action == "open_shadow":
            if plan is None or plan.phase != "entry" or not economics_passed:
                raise CashCarryShadowError("v1 attempted to open without a valid v2 execution/economics gate")
            next_active = plan
        elif step.action == "close_shadow":
            if plan is None or plan.phase != "exit":
                raise CashCarryShadowError("v1 attempted to close without a full-depth v2 exit plan")
            next_active = None
        if plan_error is not None:
            v2_action = "refuse"
            v2_reason = "full_depth_quantized_plan_unavailable_partial_fill_forbidden"
        elif not was_open and economics is not None and not economics.passed:
            v2_action = "observe"
            v2_reason = economics.reason
        else:
            v2_action = step.action
            v2_reason = step.reason
        transition = {
            "observation": snapshot.payload(),
            "observation_id": snapshot.observation_id,
            "execution_plan": plan.payload() if plan is not None else None,
            "execution_plan_refusal": plan_error,
            "break_even_gate": dataclasses.asdict(economics) if economics is not None else None,
            "v2_action": v2_action,
            "v2_reason": v2_reason,
            "legacy_v1_step": _step_payload(step),
            "state_after": _state_payload(engine, next_active),
        }
        return transition, next_active

    def _recover_unlocked(self) -> _Recovered:
        rows = self._read_rows()
        engine = CashCarryShadowEngine(self.shadow_config)
        active: Optional[QuantizedExecutionPlanV2] = None
        previous = "0" * 64
        for sequence, stored in enumerate(rows, start=1):
            snapshot = PublicMarketSnapshotV2.from_mapping(stored["observation"])
            transition, active = self._transition(engine, active, snapshot)
            core = {
                "schema_id": JOURNAL_SCHEMA_ID,
                "sequence": sequence,
                "previous_record_sha256": previous,
                "collector_config_sha256": self.collector_config.config_sha256,
                "shadow_config_sha256": self.shadow_config.config_sha256,
                **transition,
            }
            expected = {**core, "record_sha256": _sha256(core)}
            if _canonical(expected) != _canonical(stored):
                raise CashCarryShadowError(f"journal deterministic replay mismatch at line {sequence}")
            previous = stored["record_sha256"]
        return _Recovered(engine=engine, active_plan=active, records=rows)

    def recover(self) -> dict[str, Any]:
        with self._locked():
            recovered = self._recover_unlocked()
            return {
                "record_count": len(recovered.records),
                "position_open": recovered.engine.position_open,
                "positive_funding_count": recovered.engine.positive_funding_count,
                "active_quantized_plan": (
                    recovered.active_plan.payload() if recovered.active_plan is not None else None
                ),
                "last_record_sha256": (
                    recovered.records[-1]["record_sha256"] if recovered.records else None
                ),
            }

    def ingest(self, snapshot: PublicMarketSnapshotV2) -> dict[str, Any]:
        if not self.collector_config.enabled:
            return {
                "action": "disabled_noop",
                "reason": "durable_public_collector_disabled_by_default",
                "observation_id": snapshot.observation_id,
                "appended": False,
            }
        with self._locked():
            recovered = self._recover_unlocked()
            for row in recovered.records:
                if row["observation_id"] == snapshot.observation_id:
                    return {
                        "action": "duplicate_noop",
                        "reason": "observation_already_durably_committed",
                        "observation_id": snapshot.observation_id,
                        "sequence": row["sequence"],
                        "record_sha256": row["record_sha256"],
                        "appended": False,
                    }
                existing = row["observation"]
                if (
                    existing["symbol"] == snapshot.symbol
                    and existing["observed_at_ms"] == snapshot.observed_at_ms
                ):
                    raise CashCarryShadowError(
                        "same symbol/timestamp has conflicting public snapshot payload"
                    )
            transition, active = self._transition(
                recovered.engine,
                recovered.active_plan,
                snapshot,
            )
            sequence = len(recovered.records) + 1
            previous = (
                recovered.records[-1]["record_sha256"]
                if recovered.records
                else "0" * 64
            )
            core = {
                "schema_id": JOURNAL_SCHEMA_ID,
                "sequence": sequence,
                "previous_record_sha256": previous,
                "collector_config_sha256": self.collector_config.config_sha256,
                "shadow_config_sha256": self.shadow_config.config_sha256,
                **transition,
            }
            record = {**core, "record_sha256": _sha256(core)}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and stat.S_ISLNK(self.path.lstat().st_mode):
                raise CashCarryShadowError("journal symlink is forbidden")
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(self.path, flags, 0o600)
            try:
                os.fchmod(fd, 0o600)
                data = _canonical(record) + b"\n"
                if os.write(fd, data) != len(data):
                    raise CashCarryShadowError("short append to durable journal")
                os.fsync(fd)
            finally:
                os.close(fd)
            return {
                "action": record["v2_action"],
                "reason": record["v2_reason"],
                "observation_id": snapshot.observation_id,
                "sequence": sequence,
                "record_sha256": record["record_sha256"],
                "position_open": recovered.engine.position_open,
                "active_quantized_plan": active.payload() if active is not None else None,
                "break_even_gate": record["break_even_gate"],
                "execution_plan_refusal": record["execution_plan_refusal"],
                "appended": True,
            }


def snapshots_from_json(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[PublicMarketSnapshotV2]:
    rows: Sequence[Mapping[str, Any]]
    if isinstance(payload, Mapping):
        rows = payload.get("snapshots") or []
    else:
        rows = payload
    return [PublicMarketSnapshotV2.from_mapping(row) for row in rows]


__all__ = [
    "BookLevel",
    "BookWalk",
    "BreakEvenGateV2",
    "DurableCashCarryJournalV2",
    "DurableCollectorConfigV2",
    "InstrumentLegRules",
    "InstrumentRulesV2",
    "JOURNAL_SCHEMA_ID",
    "PLAN_SCHEMA_ID",
    "PublicMarketSnapshotV2",
    "QuantizedExecutionPlanV2",
    "SNAPSHOT_SCHEMA_ID",
    "build_quantized_execution_plan",
    "break_even_gate",
    "snapshots_from_json",
]
