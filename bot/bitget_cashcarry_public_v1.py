"""Strict normalization contract for public Bitget spot/perpetual carry data.

This module intentionally defines a Bitget-native source identity.  It does not
reuse or mutate the frozen Bybit snapshot schema and cannot be passed to the
Bybit durable journal.  There is no HTTP client, authentication, environment
read, private endpoint, account object, order, transfer, or withdrawal code in
this module.

The companion runner may fetch an explicitly allowlisted set of public Bitget
V2 endpoints and passes their payloads to :func:`normalize_public_payloads`.
The result is normalization/parity evidence only.  Durable station ingestion is
blocked until a separately preregistered Bitget journal/engine exists.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError


BITGET_ADAPTER_ID = "bitget_public_v2_cashcarry_v1"
BITGET_EXCHANGE_ID = "bitget"
BITGET_SOURCE_ID = "bitget_public_v2"
BITGET_PRODUCT_TYPE = "USDT-FUTURES"
BITGET_SNAPSHOT_SCHEMA_ID = "bitget_public_cashcarry_snapshot_v1"
BITGET_NORMALIZATION_SCHEMA_ID = "bitget_public_cashcarry_normalization_v1"
BITGET_STATION_COMPATIBILITY = "BLOCKED_SEPARATE_SOURCE_ENGINE_REQUIRED"


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


def _decimal(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
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
    if nonnegative and out < 0:
        raise CashCarryShadowError(f"{name} must be non-negative")
    return out


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def _exact_int(value: Any, name: str, *, nonnegative: bool = True) -> int:
    if isinstance(value, bool):
        raise CashCarryShadowError(f"{name} must be an exact integer")
    try:
        out = int(value)
        original = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise CashCarryShadowError(f"{name} must be an exact integer") from exc
    if original != Decimal(out) or (nonnegative and out < 0):
        raise CashCarryShadowError(f"{name} must be an exact integer")
    return out


def _precision_step(places: Any, name: str) -> Decimal:
    digits = _exact_int(places, name)
    if digits > 18:
        raise CashCarryShadowError(f"{name} exceeds the frozen precision limit")
    return Decimal(1).scaleb(-digits)


def _aligned(value: Decimal, step: Decimal) -> bool:
    return value % step == 0


@dataclass(frozen=True)
class BitgetBookLevelV1:
    price: str
    quantity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _decimal_text(_decimal(self.price, "book price", positive=True)))
        object.__setattr__(
            self,
            "quantity",
            _decimal_text(_decimal(self.quantity, "book quantity", positive=True)),
        )

    @property
    def price_decimal(self) -> Decimal:
        return Decimal(self.price)

    @classmethod
    def from_sequence(cls, row: Sequence[Any]) -> "BitgetBookLevelV1":
        if len(row) < 2:
            raise CashCarryShadowError("Bitget book level must contain price and quantity")
        return cls(price=str(row[0]), quantity=str(row[1]))


@dataclass(frozen=True)
class BitgetInstrumentLegRulesV1:
    market: str
    tick_size: str
    qty_step: str
    min_order_qty: str
    min_notional_usdt: str
    min_order_qty_source: str
    status: str
    taker_fee_rate_public_default: str

    def __post_init__(self) -> None:
        if self.market not in {"spot", "usdt_perpetual"}:
            raise CashCarryShadowError("Bitget leg market is invalid")
        for name in ("tick_size", "qty_step", "min_order_qty", "min_notional_usdt"):
            value = _decimal(getattr(self, name), name, positive=True)
            object.__setattr__(self, name, _decimal_text(value))
        fee = _decimal(self.taker_fee_rate_public_default, "public taker fee", nonnegative=True)
        object.__setattr__(self, "taker_fee_rate_public_default", _decimal_text(fee))
        if not _aligned(Decimal(self.min_order_qty), Decimal(self.qty_step)):
            raise CashCarryShadowError("Bitget minimum quantity is not qty-step aligned")
        expected_status = "online" if self.market == "spot" else "normal"
        if self.status != expected_status:
            raise CashCarryShadowError(f"Bitget {self.market} instrument is not tradable")
        allowed_sources = {
            "spot": "DERIVED_LOWEST_POSITIVE_QTY_STEP_OFFICIAL_MIN_TRADE_AMOUNT_OBSOLETE",
            "usdt_perpetual": "OFFICIAL_MIN_TRADE_NUM",
        }
        if self.min_order_qty_source != allowed_sources[self.market]:
            raise CashCarryShadowError("Bitget minimum quantity provenance mismatch")


@dataclass(frozen=True)
class BitgetInstrumentRulesV1:
    symbol: str
    product_type: str
    funding_interval_minutes: int
    spot: BitgetInstrumentLegRulesV1
    usdt_perpetual: BitgetInstrumentLegRulesV1
    spot_price_precision: int
    spot_quantity_precision: int
    perp_price_place: int
    perp_price_end_step: str
    perp_size_multiplier: str

    def __post_init__(self) -> None:
        symbol = str(self.symbol).strip().upper()
        if not symbol.endswith("USDT"):
            raise CashCarryShadowError("Bitget symbol must be an explicit USDT pair")
        object.__setattr__(self, "symbol", symbol)
        if self.product_type != BITGET_PRODUCT_TYPE:
            raise CashCarryShadowError("Bitget product type must be USDT-FUTURES")
        interval = _exact_int(self.funding_interval_minutes, "funding interval")
        if interval <= 0:
            raise CashCarryShadowError("Bitget funding interval must be positive")
        object.__setattr__(self, "funding_interval_minutes", interval)
        for name in ("spot_price_precision", "spot_quantity_precision", "perp_price_place"):
            object.__setattr__(self, name, _exact_int(getattr(self, name), name))
        object.__setattr__(
            self,
            "perp_price_end_step",
            _decimal_text(_decimal(self.perp_price_end_step, "priceEndStep", positive=True)),
        )
        object.__setattr__(
            self,
            "perp_size_multiplier",
            _decimal_text(_decimal(self.perp_size_multiplier, "sizeMultiplier", positive=True)),
        )

    def payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class BitgetFundingSettlementV1:
    settled_at_ms: int
    rate: float
    perp_mark_price_proxy: float | None = None

    def __post_init__(self) -> None:
        _exact_int(self.settled_at_ms, "funding time")
        rate = float(_decimal(self.rate, "Bitget funding rate"))
        object.__setattr__(self, "rate", rate)
        if self.perp_mark_price_proxy is not None:
            _decimal(self.perp_mark_price_proxy, "mark price proxy", positive=True)

    @property
    def settlement_id(self) -> str:
        return _sha256({"settled_at_ms": self.settled_at_ms, "rate": self.rate})


def _validate_book(
    bids: tuple[BitgetBookLevelV1, ...],
    asks: tuple[BitgetBookLevelV1, ...],
    rules: BitgetInstrumentLegRulesV1,
    label: str,
) -> None:
    if not bids or not asks:
        raise CashCarryShadowError(f"Bitget {label} book is incomplete")
    bid_prices = [row.price_decimal for row in bids]
    ask_prices = [row.price_decimal for row in asks]
    if bid_prices != sorted(bid_prices, reverse=True) or len(set(bid_prices)) != len(bid_prices):
        raise CashCarryShadowError(f"Bitget {label} bids must be unique descending")
    if ask_prices != sorted(ask_prices) or len(set(ask_prices)) != len(ask_prices):
        raise CashCarryShadowError(f"Bitget {label} asks must be unique ascending")
    if bid_prices[0] > ask_prices[0]:
        raise CashCarryShadowError(f"Bitget {label} book is crossed")
    step = Decimal(rules.tick_size)
    if any(not _aligned(level.price_decimal, step) for level in (*bids, *asks)):
        raise CashCarryShadowError(f"Bitget {label} book price is off tick")


@dataclass(frozen=True)
class BitgetPublicCashCarrySnapshotV1:
    symbol: str
    observed_at_ms: int
    spot_book_ts_ms: int
    perp_book_ts_ms: int
    spot_bids: tuple[BitgetBookLevelV1, ...]
    spot_asks: tuple[BitgetBookLevelV1, ...]
    perp_bids: tuple[BitgetBookLevelV1, ...]
    perp_asks: tuple[BitgetBookLevelV1, ...]
    projected_funding_rate: float
    next_funding_time_ms: int
    funding_settlements: tuple[BitgetFundingSettlementV1, ...]
    instruments: BitgetInstrumentRulesV1
    adapter_id: str = BITGET_ADAPTER_ID
    exchange_id: str = BITGET_EXCHANGE_ID
    source: str = BITGET_SOURCE_ID
    complete: bool = True

    def __post_init__(self) -> None:
        if self.adapter_id != BITGET_ADAPTER_ID:
            raise CashCarryShadowError("Bitget adapter identity mismatch")
        if self.exchange_id != BITGET_EXCHANGE_ID or self.source != BITGET_SOURCE_ID:
            raise CashCarryShadowError("Bitget exchange/source identity mismatch")
        symbol = str(self.symbol).strip().upper()
        if symbol != self.instruments.symbol:
            raise CashCarryShadowError("Bitget snapshot/instrument symbol mismatch")
        object.__setattr__(self, "symbol", symbol)
        for name in ("observed_at_ms", "spot_book_ts_ms", "perp_book_ts_ms", "next_funding_time_ms"):
            _exact_int(getattr(self, name), name)
        if self.spot_book_ts_ms > self.observed_at_ms or self.perp_book_ts_ms > self.observed_at_ms:
            raise CashCarryShadowError("future Bitget book timestamp is forbidden")
        if self.next_funding_time_ms <= self.observed_at_ms:
            raise CashCarryShadowError("Bitget next funding time must be in the future")
        projected = float(_decimal(self.projected_funding_rate, "Bitget projected funding"))
        object.__setattr__(self, "projected_funding_rate", projected)
        if self.complete is not True:
            raise CashCarryShadowError("incomplete Bitget snapshots are forbidden")
        for name in ("spot_bids", "spot_asks", "perp_bids", "perp_asks"):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, BitgetBookLevelV1) for item in values):
                raise CashCarryShadowError(f"{name} must contain BitgetBookLevelV1")
            object.__setattr__(self, name, values)
        _validate_book(self.spot_bids, self.spot_asks, self.instruments.spot, "spot")
        _validate_book(self.perp_bids, self.perp_asks, self.instruments.usdt_perpetual, "perp")
        settlements = tuple(self.funding_settlements)
        if list(settlements) != sorted(settlements, key=lambda row: row.settled_at_ms):
            raise CashCarryShadowError("Bitget funding settlements must be ascending")
        if len({row.settlement_id for row in settlements}) != len(settlements):
            raise CashCarryShadowError("duplicate Bitget funding settlement")
        if any(row.settled_at_ms > self.observed_at_ms for row in settlements):
            raise CashCarryShadowError("future Bitget funding settlement is forbidden")
        object.__setattr__(self, "funding_settlements", settlements)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_id": BITGET_SNAPSHOT_SCHEMA_ID,
            "adapter_id": self.adapter_id,
            "exchange_id": self.exchange_id,
            "source": self.source,
            "symbol": self.symbol,
            "observed_at_ms": self.observed_at_ms,
            "spot_book_ts_ms": self.spot_book_ts_ms,
            "perp_book_ts_ms": self.perp_book_ts_ms,
            "spot_bids": [dataclasses.asdict(row) for row in self.spot_bids],
            "spot_asks": [dataclasses.asdict(row) for row in self.spot_asks],
            "perp_bids": [dataclasses.asdict(row) for row in self.perp_bids],
            "perp_asks": [dataclasses.asdict(row) for row in self.perp_asks],
            "projected_funding_rate": self.projected_funding_rate,
            "next_funding_time_ms": self.next_funding_time_ms,
            "funding_settlements": [dataclasses.asdict(row) for row in self.funding_settlements],
            "instruments": self.instruments.payload(),
            "complete": self.complete,
            "station_compatibility": BITGET_STATION_COMPATIBILITY,
        }

    @property
    def observation_id(self) -> str:
        return _sha256(self.payload())


def _success(payload: Mapping[str, Any], label: str) -> Any:
    if str(payload.get("code") or "") != "00000":
        raise CashCarryShadowError(f"Bitget {label} response code is not 00000")
    if str(payload.get("msg") or "").lower() != "success":
        raise CashCarryShadowError(f"Bitget {label} response is not success")
    if "data" not in payload:
        raise CashCarryShadowError(f"Bitget {label} response is missing data")
    return payload["data"]


def _one_symbol(data: Any, symbol: str, label: str) -> Mapping[str, Any]:
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], Mapping):
        raise CashCarryShadowError(f"Bitget {label} must contain exactly one symbol")
    row = data[0]
    if str(row.get("symbol") or "").upper() != symbol:
        raise CashCarryShadowError(f"Bitget {label} symbol mismatch")
    return row


def _levels(data: Mapping[str, Any], side: str, label: str) -> tuple[BitgetBookLevelV1, ...]:
    rows = data.get(side)
    if not isinstance(rows, list) or not rows:
        raise CashCarryShadowError(f"Bitget {label} is missing {side}")
    return tuple(BitgetBookLevelV1.from_sequence(row) for row in rows)


def normalize_public_payloads(
    payloads: Mapping[str, Mapping[str, Any]],
    *,
    symbol: str,
    funding_proxy_max_lag_ms: int = 120_000,
) -> BitgetPublicCashCarrySnapshotV1:
    """Normalize one complete seven-response Bitget public snapshot."""

    symbol = str(symbol).strip().upper()
    required = {
        "spot_instrument",
        "spot_book",
        "perp_instrument",
        "perp_book",
        "current_funding",
        "funding_history",
        "server_time",
    }
    if set(payloads) != required:
        raise CashCarryShadowError("Bitget public payload set is incomplete or contains extras")
    spot_row = _one_symbol(_success(payloads["spot_instrument"], "spot instrument"), symbol, "spot instrument")
    perp_row = _one_symbol(_success(payloads["perp_instrument"], "perp instrument"), symbol, "perp instrument")
    funding_row = _one_symbol(_success(payloads["current_funding"], "current funding"), symbol, "current funding")
    spot_book = _success(payloads["spot_book"], "spot book")
    perp_book = _success(payloads["perp_book"], "perp book")
    history = _success(payloads["funding_history"], "funding history")
    server = _success(payloads["server_time"], "server time")
    if not isinstance(spot_book, Mapping) or not isinstance(perp_book, Mapping):
        raise CashCarryShadowError("Bitget book data must be objects")
    if not isinstance(server, Mapping):
        raise CashCarryShadowError("Bitget server time data must be an object")
    if str(spot_row.get("quoteCoin") or "").upper() != "USDT":
        raise CashCarryShadowError("Bitget spot quote coin is not USDT")
    if str(perp_row.get("quoteCoin") or "").upper() != "USDT":
        raise CashCarryShadowError("Bitget perpetual quote coin is not USDT")
    if str(perp_row.get("symbolType") or "").lower() != "perpetual":
        raise CashCarryShadowError("Bitget contract is not perpetual")
    margins = {str(item).upper() for item in (perp_row.get("supportMarginCoins") or [])}
    if "USDT" not in margins:
        raise CashCarryShadowError("Bitget perpetual does not support USDT margin")

    spot_price_precision = _exact_int(spot_row.get("pricePrecision"), "spot pricePrecision")
    spot_quantity_precision = _exact_int(spot_row.get("quantityPrecision"), "spot quantityPrecision")
    spot_tick = _precision_step(spot_price_precision, "spot pricePrecision")
    spot_qty_step = _precision_step(spot_quantity_precision, "spot quantityPrecision")
    perp_price_place = _exact_int(perp_row.get("pricePlace"), "perp pricePlace")
    perp_end_step = _decimal(perp_row.get("priceEndStep"), "perp priceEndStep", positive=True)
    perp_tick = _precision_step(perp_price_place, "perp pricePlace") * perp_end_step
    perp_qty_step = _decimal(perp_row.get("sizeMultiplier"), "perp sizeMultiplier", positive=True)
    perp_min_qty = _decimal(perp_row.get("minTradeNum"), "perp minTradeNum", positive=True)
    spot_rules = BitgetInstrumentLegRulesV1(
        market="spot",
        tick_size=_decimal_text(spot_tick),
        qty_step=_decimal_text(spot_qty_step),
        min_order_qty=_decimal_text(spot_qty_step),
        min_notional_usdt=str(spot_row.get("minTradeUSDT") or ""),
        min_order_qty_source="DERIVED_LOWEST_POSITIVE_QTY_STEP_OFFICIAL_MIN_TRADE_AMOUNT_OBSOLETE",
        status=str(spot_row.get("status") or ""),
        taker_fee_rate_public_default=str(spot_row.get("takerFeeRate") or ""),
    )
    perp_rules = BitgetInstrumentLegRulesV1(
        market="usdt_perpetual",
        tick_size=_decimal_text(perp_tick),
        qty_step=_decimal_text(perp_qty_step),
        min_order_qty=_decimal_text(perp_min_qty),
        min_notional_usdt=str(perp_row.get("minTradeUSDT") or ""),
        min_order_qty_source="OFFICIAL_MIN_TRADE_NUM",
        status=str(perp_row.get("symbolStatus") or ""),
        taker_fee_rate_public_default=str(perp_row.get("takerFeeRate") or ""),
    )
    contract_hours = _exact_int(perp_row.get("fundInterval"), "contract fundInterval")
    current_hours = _exact_int(funding_row.get("fundingRateInterval"), "current funding interval")
    if contract_hours != current_hours:
        raise CashCarryShadowError("Bitget contract/current funding interval mismatch")
    instruments = BitgetInstrumentRulesV1(
        symbol=symbol,
        product_type=BITGET_PRODUCT_TYPE,
        funding_interval_minutes=contract_hours * 60,
        spot=spot_rules,
        usdt_perpetual=perp_rules,
        spot_price_precision=spot_price_precision,
        spot_quantity_precision=spot_quantity_precision,
        perp_price_place=perp_price_place,
        perp_price_end_step=_decimal_text(perp_end_step),
        perp_size_multiplier=_decimal_text(perp_qty_step),
    )
    actual_perp_scale = _decimal(perp_book.get("scale"), "perp scale", positive=True)
    if actual_perp_scale != perp_tick or str(perp_book.get("precision")) != "scale0":
        raise CashCarryShadowError("Bitget unmerged perp book scale differs from contract tick")

    observed_at = _exact_int(server.get("serverTime"), "server time")
    for label, payload in payloads.items():
        request_time = _exact_int(payload.get("requestTime"), f"{label} requestTime")
        if request_time > observed_at:
            raise CashCarryShadowError(f"Bitget {label} requestTime is after final server time")
    spot_ts = _exact_int(spot_book.get("ts"), "spot book ts")
    perp_ts = _exact_int(perp_book.get("ts"), "perp book ts")
    perp_bids = _levels(perp_book, "bids", "perp book")
    perp_asks = _levels(perp_book, "asks", "perp book")
    perp_mid = (float(perp_bids[0].price) + float(perp_asks[0].price)) / 2.0

    if not isinstance(history, list):
        raise CashCarryShadowError("Bitget funding history must be a list")
    settlements: list[BitgetFundingSettlementV1] = []
    seen_times: set[int] = set()
    for row in history:
        if not isinstance(row, Mapping) or str(row.get("symbol") or "").upper() != symbol:
            raise CashCarryShadowError("Bitget funding history row symbol mismatch")
        settled = _exact_int(row.get("fundingTime"), "funding history time")
        if settled in seen_times:
            raise CashCarryShadowError("duplicate Bitget funding history timestamp")
        seen_times.add(settled)
        if settled > observed_at:
            raise CashCarryShadowError("future Bitget funding history row")
        proxy = perp_mid if observed_at - settled <= funding_proxy_max_lag_ms else None
        settlements.append(
            BitgetFundingSettlementV1(
                settled_at_ms=settled,
                rate=float(_decimal(row.get("fundingRate"), "funding history rate")),
                perp_mark_price_proxy=proxy,
            )
        )
    settlements.sort(key=lambda row: row.settled_at_ms)
    snapshot = BitgetPublicCashCarrySnapshotV1(
        symbol=symbol,
        observed_at_ms=observed_at,
        spot_book_ts_ms=spot_ts,
        perp_book_ts_ms=perp_ts,
        spot_bids=_levels(spot_book, "bids", "spot book"),
        spot_asks=_levels(spot_book, "asks", "spot book"),
        perp_bids=perp_bids,
        perp_asks=perp_asks,
        projected_funding_rate=float(
            _decimal(funding_row.get("fundingRate"), "current funding rate")
        ),
        next_funding_time_ms=_exact_int(funding_row.get("nextUpdate"), "next funding time"),
        funding_settlements=tuple(settlements),
        instruments=instruments,
    )
    return snapshot


def normalization_receipt(snapshot: BitgetPublicCashCarrySnapshotV1) -> dict[str, Any]:
    return {
        "schema_id": BITGET_NORMALIZATION_SCHEMA_ID,
        "adapter_id": BITGET_ADAPTER_ID,
        "exchange_id": BITGET_EXCHANGE_ID,
        "source_id": BITGET_SOURCE_ID,
        "research_only": True,
        "executable": False,
        "broker_calls": False,
        "private_api_calls": False,
        "api_keys_or_environment_reads": False,
        "orders_transfers_withdrawals": False,
        "symbol": snapshot.symbol,
        "observation_id": snapshot.observation_id,
        "snapshot": snapshot.payload(),
        "station_compatibility": BITGET_STATION_COMPATIBILITY,
        "blockers": [
            "separate Bitget durable hash-chain journal and deterministic replay contract",
            "Bitget-native quantized execution/economics engine",
            "account-specific Bitget fee-tier and transfer/reconciliation receipt",
            "cross-exchange capital, outage, margin, liquidation, and two-leg recovery model",
        ],
        "performance_claims": False,
    }


__all__ = [
    "BITGET_ADAPTER_ID",
    "BITGET_EXCHANGE_ID",
    "BITGET_PRODUCT_TYPE",
    "BITGET_SOURCE_ID",
    "BITGET_STATION_COMPATIBILITY",
    "BitgetBookLevelV1",
    "BitgetFundingSettlementV1",
    "BitgetInstrumentLegRulesV1",
    "BitgetInstrumentRulesV1",
    "BitgetPublicCashCarrySnapshotV1",
    "normalize_public_payloads",
    "normalization_receipt",
]
