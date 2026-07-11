"""Typed contracts for the research-only FX/CFD V2 branch.

The legacy FX paths mix detection, entry and execution assumptions.  V2 keeps
them explicit: a strategy emits an immutable event and trade plan, while the
execution harness decides whether that plan could have filled on later bars.
Nothing in this module can place an order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FxEvent:
    event_id: str
    family: str
    side: str
    signal_ts: int
    level: float
    level_kind: str
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.side not in {"long", "short"}:
            raise ValueError("FxEvent.side must be long or short")
        if not self.event_id:
            raise ValueError("FxEvent.event_id is required")
        if self.signal_ts <= 0 or not math.isfinite(float(self.level)) or self.level <= 0:
            raise ValueError("FxEvent requires positive finite signal_ts and level")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FxTradePlan:
    event: FxEvent
    entry_type: str                 # market_next_open | limit
    reference_price: float          # signal close; gap/chase anchor
    stop_price: float
    target_rr: float
    max_hold_bars: int
    validity_bars: int = 1
    limit_price: Optional[float] = None
    target_price: Optional[float] = None
    max_entry_gap_atr: float = 0.40
    allowed_fill_sessions: tuple[str, ...] = ()
    execution_bar_seconds: int = 3600
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.entry_type not in {"market_next_open", "limit"}:
            raise ValueError("entry_type must be market_next_open or limit")
        if not all(math.isfinite(float(value)) for value in (
            self.reference_price, self.stop_price, self.target_rr,
            self.max_entry_gap_atr,
        )):
            raise ValueError("trade plan numeric fields must be finite")
        if self.reference_price <= 0 or self.stop_price <= 0:
            raise ValueError("reference and stop prices must be positive")
        if self.target_rr <= 0 or self.max_hold_bars <= 0:
            raise ValueError("target_rr and max_hold_bars must be positive")
        if self.entry_type == "limit" and not (self.limit_price and self.limit_price > 0):
            raise ValueError("limit plan requires a positive limit_price")
        if self.limit_price is not None and not math.isfinite(float(self.limit_price)):
            raise ValueError("limit_price must be finite")
        if self.target_price is not None and not (
            math.isfinite(float(self.target_price)) and self.target_price > 0
        ):
            raise ValueError("target_price must be positive and finite")
        if self.validity_bars <= 0:
            raise ValueError("validity_bars must be positive")
        if self.max_entry_gap_atr < 0:
            raise ValueError("max_entry_gap_atr must be non-negative")
        if self.execution_bar_seconds <= 0:
            raise ValueError("execution_bar_seconds must be positive")
        if self.event.signal_ts <= 0:
            raise ValueError("event.signal_ts must be the positive decision timestamp")
        if self.event.side == "long" and self.stop_price >= self.reference_price:
            raise ValueError("long stop must be below the reference price")
        if self.event.side == "short" and self.stop_price <= self.reference_price:
            raise ValueError("short stop must be above the reference price")
        entry_anchor = float(self.limit_price) if self.entry_type == "limit" else self.reference_price
        if self.event.side == "long" and self.stop_price >= entry_anchor:
            raise ValueError("long stop must be below the planned entry")
        if self.event.side == "short" and self.stop_price <= entry_anchor:
            raise ValueError("short stop must be above the planned entry")
        if self.target_price is not None:
            if self.event.side == "long" and self.target_price <= entry_anchor:
                raise ValueError("long target must be above the planned entry")
            if self.event.side == "short" and self.target_price >= entry_anchor:
                raise ValueError("short target must be below the planned entry")

    @property
    def side(self) -> str:
        return self.event.side

    @property
    def strategy(self) -> str:
        return self.event.family

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["side"] = self.side
        out["strategy"] = self.strategy
        return out


@dataclass(frozen=True)
class FxExecutionCosts:
    """Universal price-bps cost contract.

    ``spread_bps`` is paid once per round trip.  Commission is per side.
    Slippage is adverse and side-specific.  Financing is charged by elapsed
    wall-clock days.  These are research assumptions until calibrated to fills.
    """

    spread_bps: float
    commission_bps_per_side: float
    market_entry_slippage_bps: float
    limit_entry_slippage_bps: float
    exit_slippage_bps: float
    financing_bps_per_day: float = 0.0
    label: str = "base"

    def __post_init__(self) -> None:
        values = (
            self.spread_bps, self.commission_bps_per_side,
            self.market_entry_slippage_bps, self.limit_entry_slippage_bps,
            self.exit_slippage_bps, self.financing_bps_per_day,
        )
        if not all(math.isfinite(float(value)) and float(value) >= 0 for value in values):
            raise ValueError("execution costs must be finite and non-negative")

    def round_trip_bps(self, entry_type: str) -> float:
        entry_slip = (
            self.limit_entry_slippage_bps
            if entry_type == "limit"
            else self.market_entry_slippage_bps
        )
        return max(
            0.0,
            float(self.spread_bps)
            + 2.0 * float(self.commission_bps_per_side)
            + float(entry_slip)
            + float(self.exit_slippage_bps),
        )

    def non_spread_bps(self, entry_type: str) -> float:
        """Fees/slippage not already embedded in synthetic bid/ask quotes."""
        return max(0.0, self.round_trip_bps(entry_type) - float(self.spread_bps))


@dataclass(frozen=True)
class FxInstrumentSpec:
    symbol: str
    asset_class: str                # fx | cfd
    pip_size: float
    price_precision: int
    schedule: str                   # fx_24x5 | xau_23x5
    round_steps: tuple[float, ...]
    base_costs: FxExecutionCosts
    stress_costs: FxExecutionCosts
    notes: str = ""

    def __post_init__(self) -> None:
        if self.asset_class not in {"fx", "cfd"}:
            raise ValueError("asset_class must be fx or cfd")
        if self.pip_size <= 0:
            raise ValueError("pip_size must be positive")


@dataclass
class FxContext:
    symbol: str
    ts: int                           # decision timestamp
    bar_ts: int                       # source candle-open timestamp
    bar_seconds: int
    price: float
    atr: float
    sessions: tuple[str, ...]
    news_allowed: bool
    news_reason: str
    levels: Any
    range_state: Any
    regime_state: Any
    elder_state: Any
    round_levels: tuple[float, ...]


@dataclass
class FxBacktestResult:
    trades: list[Dict[str, Any]] = field(default_factory=list)
    signal_ledger: list[Dict[str, Any]] = field(default_factory=list)
    signals: int = 0
    orders_placed: int = 0
    unfilled: int = 0
    duplicate_events: int = 0
    invalid_plans: int = 0
    skipped_gap: int = 0
    skipped_rr: int = 0
    blocked_fill_window: int = 0
    censored_orders: int = 0
    censored_trades: int = 0

    def diagnostics(self) -> Dict[str, Any]:
        eligible_orders = max(0, self.orders_placed - self.censored_orders)
        filled_attempts = len(self.trades) + self.censored_trades
        return {
            "signals": self.signals,
            "orders_placed": self.orders_placed,
            "unfilled": self.unfilled,
            "unfilled_rate": self.unfilled / self.orders_placed if self.orders_placed else 0.0,
            "duplicate_events": self.duplicate_events,
            "invalid_plans": self.invalid_plans,
            "skipped_gap": self.skipped_gap,
            "skipped_rr": self.skipped_rr,
            "blocked_fill_window": self.blocked_fill_window,
            "duplicate_event_rate": self.duplicate_events / self.signals if self.signals else 0.0,
            "censored_orders": self.censored_orders,
            "censored_trades": self.censored_trades,
            "censored_order_rate": (
                self.censored_orders / self.orders_placed if self.orders_placed else 0.0
            ),
            "censored_trade_rate": (
                self.censored_trades / filled_attempts if filled_attempts else 0.0
            ),
            "fill_rate": (
                filled_attempts / eligible_orders if eligible_orders else 0.0
            ),
        }
