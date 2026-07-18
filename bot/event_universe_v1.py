"""Causal research-only universe for fresh crypto events.

The live symbol router intentionally prefers mature, liquid instruments.  That
is a sensible money-safety default, but it means newly active symbols can be
discarded before any setup geometry is built.  This module defines a separate
point-in-time discovery contract for those symbols.

It is deliberately pure: no HTTP, environment, filesystem, account, order,
position, risk, Telegram or live-router imports.  A companion runner may feed
public Bybit payloads into these functions and persist research receipts.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from dataclasses import dataclass
from statistics import median
from typing import Any, Mapping, Sequence


RESEARCH_ONLY = True
EXECUTABLE = False
LIVE_READY = False
SOURCE_ID = "bybit_public_v5"
CONFIG_SCHEMA_ID = "event_universe_config_v1"
SNAPSHOT_SCHEMA_ID = "event_universe_snapshot_v1"
MARKET_ROW_SCHEMA_ID = "event_universe_market_row_v1"
SCORE_SCHEMA_ID = "event_universe_score_v1"
M5_INTERVAL_MS = 5 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,28}USDT$")


class EventUniverseError(ValueError):
    """The point-in-time research input is incomplete, unsafe, or inconsistent."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _finite_float(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise EventUniverseError(f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EventUniverseError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise EventUniverseError(f"{name} must be finite")
    if positive and result <= 0:
        raise EventUniverseError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise EventUniverseError(f"{name} must be non-negative")
    return result


def _exact_int(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> int:
    if isinstance(value, bool):
        raise EventUniverseError(f"{name} must be an exact integer")
    try:
        result = int(value)
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise EventUniverseError(f"{name} must be an exact integer") from exc
    if not math.isfinite(numeric) or numeric != float(result):
        raise EventUniverseError(f"{name} must be an exact integer")
    if positive and result <= 0:
        raise EventUniverseError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise EventUniverseError(f"{name} must be non-negative")
    return result


@dataclass(frozen=True)
class EventUniverseConfigV1:
    schema_id: str = CONFIG_SCHEMA_ID
    source_id: str = SOURCE_ID
    interval: str = "5"
    recent_bars: int = 3
    baseline_bars: int = 72
    min_listing_age_hours: int = 24
    normal_listing_age_days: int = 7
    min_turnover_24h_usd: float = 1_000_000.0
    max_spread_bps: float = 35.0
    min_recent_quote_usd: float = 100_000.0
    min_inflow_mult: float = 1.5
    min_inflow_z: float = 1.5
    max_abs_recent_return_pct: float = 18.0
    min_range_expansion_atr: float = 1.0
    max_prefetch_symbols: int = 100
    top_k: int = 32
    poll_interval_seconds: int = 300
    max_cycle_seconds: int = 240
    max_source_time_skew_ms: int = 120_000
    max_runtime_seconds: int = 7 * 24 * 60 * 60
    max_snapshots: int = 2016
    max_total_bytes: int = 512 * 1024 * 1024
    min_free_bytes: int = 20 * 1024 * 1024 * 1024
    max_response_bytes: int = 8 * 1024 * 1024
    max_replay_uncompressed_bytes: int = 16 * 1024 * 1024
    public_requests_per_second: float = 2.0

    def __post_init__(self) -> None:
        if self.schema_id != CONFIG_SCHEMA_ID or self.source_id != SOURCE_ID:
            raise EventUniverseError("event-universe config identity mismatch")
        if self.interval != "5":
            raise EventUniverseError("event-universe v1 is frozen to closed M5")
        for name in (
            "recent_bars",
            "baseline_bars",
            "min_listing_age_hours",
            "normal_listing_age_days",
            "max_prefetch_symbols",
            "top_k",
            "poll_interval_seconds",
            "max_cycle_seconds",
            "max_source_time_skew_ms",
            "max_runtime_seconds",
            "max_snapshots",
            "max_total_bytes",
            "min_free_bytes",
            "max_response_bytes",
            "max_replay_uncompressed_bytes",
        ):
            if _exact_int(getattr(self, name), name, positive=True) != getattr(self, name):
                raise EventUniverseError(f"{name} must be a positive integer")
        if self.baseline_bars < self.recent_bars + 10:
            raise EventUniverseError("baseline must materially exceed recent window")
        if self.normal_listing_age_days * 24 <= self.min_listing_age_hours:
            raise EventUniverseError("normal listing boundary must exceed fresh boundary")
        if self.top_k > self.max_prefetch_symbols:
            raise EventUniverseError("top_k cannot exceed max_prefetch_symbols")
        if self.max_cycle_seconds >= self.poll_interval_seconds:
            raise EventUniverseError("cycle wall-clock cap must be below the poll interval")
        for name in (
            "min_turnover_24h_usd",
            "max_spread_bps",
            "min_recent_quote_usd",
            "min_inflow_mult",
            "min_inflow_z",
            "max_abs_recent_return_pct",
            "min_range_expansion_atr",
            "public_requests_per_second",
        ):
            _finite_float(getattr(self, name), name, positive=True)
        if self.public_requests_per_second > 10:
            raise EventUniverseError("public request rate is not conservatively bounded")

    @property
    def required_closed_bars(self) -> int:
        return self.baseline_bars + self.recent_bars

    @property
    def config_sha256(self) -> str:
        return sha256_payload(dataclasses.asdict(self))


@dataclass(frozen=True)
class MarketEligibilityV1:
    symbol: str
    eligible: bool
    reason: str
    listing_tier: str
    listing_age_hours: float
    turnover_24h_usd: float
    bid: float
    ask: float
    spread_bps: float
    price_24h_pct: float
    prefetch_proxy: float

    def payload(self) -> dict[str, Any]:
        return {"schema_id": MARKET_ROW_SCHEMA_ID, **dataclasses.asdict(self)}


def evaluate_market_eligibility(
    instrument: Mapping[str, Any],
    ticker: Mapping[str, Any] | None,
    *,
    as_of_ms: int,
    config: EventUniverseConfigV1,
) -> MarketEligibilityV1:
    """Evaluate one instrument using only the same point-in-time public snapshot."""
    as_of_ms = _exact_int(as_of_ms, "as_of_ms", positive=True)
    symbol = str(instrument.get("symbol") or "").strip().upper()
    empty = dict(
        symbol=symbol,
        eligible=False,
        listing_tier="rejected",
        listing_age_hours=-1.0,
        turnover_24h_usd=0.0,
        bid=0.0,
        ask=0.0,
        spread_bps=0.0,
        price_24h_pct=0.0,
        prefetch_proxy=0.0,
    )

    def reject(reason: str, **updates: Any) -> MarketEligibilityV1:
        return MarketEligibilityV1(reason=reason, **{**empty, **updates})

    if not _SYMBOL_RE.fullmatch(symbol):
        return reject("symbol_not_usdt_perpetual_shape")
    if str(instrument.get("status") or "") != "Trading":
        return reject("instrument_not_trading")
    if str(instrument.get("contractType") or "") != "LinearPerpetual":
        return reject("instrument_not_linear_perpetual")
    if str(instrument.get("quoteCoin") or "") != "USDT" or str(instrument.get("settleCoin") or "") != "USDT":
        return reject("instrument_not_usdt_quoted_and_settled")
    try:
        launch_ms = _exact_int(instrument.get("launchTime"), "launchTime", positive=True)
    except EventUniverseError:
        return reject("launch_time_missing_or_invalid")
    if launch_ms > as_of_ms:
        return reject("launch_time_in_future")
    age_hours = (as_of_ms - launch_ms) / 3_600_000.0
    age_updates = {"listing_age_hours": round(age_hours, 6)}
    if age_hours < config.min_listing_age_hours:
        return reject("listing_younger_than_frozen_minimum", **age_updates)
    tier = "normal" if age_hours >= config.normal_listing_age_days * 24 else "fresh_shadow"
    empty.update(age_updates)
    empty["listing_tier"] = tier

    if not isinstance(ticker, Mapping):
        return reject("ticker_missing", **empty)
    if str(ticker.get("symbol") or "").strip().upper() != symbol:
        return reject("ticker_symbol_mismatch", **empty)
    try:
        turnover = _finite_float(ticker.get("turnover24h"), "turnover24h", nonnegative=True)
        bid = _finite_float(ticker.get("bid1Price"), "bid1Price", positive=True)
        ask = _finite_float(ticker.get("ask1Price"), "ask1Price", positive=True)
        if ticker.get("price24hPcnt") in (None, ""):
            raise EventUniverseError("price24hPcnt is missing")
        price_24h = _finite_float(ticker.get("price24hPcnt"), "price24hPcnt") * 100.0
    except EventUniverseError as exc:
        return reject(f"ticker_invalid:{exc}", **empty)
    if ask < bid:
        crossed_updates = {**empty, "turnover_24h_usd": turnover, "bid": bid, "ask": ask}
        return reject("ticker_book_crossed", **crossed_updates)
    mid = (bid + ask) / 2.0
    spread_bps = (ask - bid) / mid * 10_000.0
    updates = {
        **empty,
        "turnover_24h_usd": turnover,
        "bid": bid,
        "ask": ask,
        "spread_bps": round(spread_bps, 6),
        "price_24h_pct": round(price_24h, 6),
    }
    if turnover < config.min_turnover_24h_usd:
        return reject("turnover_24h_below_floor", **updates)
    if spread_bps > config.max_spread_bps:
        return reject("spread_above_frozen_cap", **updates)
    turnover_units = max(1.0, turnover / config.min_turnover_24h_usd)
    proxy = abs(price_24h) * math.log1p(turnover_units)
    return MarketEligibilityV1(
        symbol=symbol,
        eligible=True,
        reason="eligible",
        listing_tier=tier,
        listing_age_hours=round(age_hours, 6),
        turnover_24h_usd=turnover,
        bid=bid,
        ask=ask,
        spread_bps=round(spread_bps, 6),
        price_24h_pct=round(price_24h, 6),
        prefetch_proxy=round(proxy, 9),
    )


def select_prefetch_symbols(
    rows: Sequence[MarketEligibilityV1],
    *,
    config: EventUniverseConfigV1,
) -> tuple[str, ...]:
    """Bound M5 calls while preserving both event movers and liquid controls."""
    eligible = {row.symbol: row for row in rows if row.eligible}
    if len(eligible) <= config.max_prefetch_symbols:
        return tuple(sorted(eligible))
    event_slots = config.max_prefetch_symbols * 2 // 3
    event_rank = sorted(
        eligible.values(),
        key=lambda row: (-row.prefetch_proxy, -row.turnover_24h_usd, row.symbol),
    )
    liquid_rank = sorted(
        eligible.values(),
        key=lambda row: (-row.turnover_24h_usd, -row.prefetch_proxy, row.symbol),
    )
    chosen: list[str] = [row.symbol for row in event_rank[:event_slots]]
    chosen_set = set(chosen)
    for row in liquid_rank:
        if len(chosen) >= config.max_prefetch_symbols:
            break
        if row.symbol not in chosen_set:
            chosen.append(row.symbol)
            chosen_set.add(row.symbol)
    return tuple(chosen)


@dataclass(frozen=True)
class ClosedM5V1:
    start_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_turnover: float

    def payload(self) -> list[Any]:
        return [
            self.start_ms,
            self.open,
            self.high,
            self.low,
            self.close,
            self.base_volume,
            self.quote_turnover,
        ]


def closed_contiguous_m5(
    raw_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    required_bars: int,
) -> tuple[ClosedM5V1, ...]:
    """Normalize reverse/ascending REST rows and fail closed on the usable tail."""
    as_of_ms = _exact_int(as_of_ms, "as_of_ms", positive=True)
    required_bars = _exact_int(required_bars, "required_bars", positive=True)
    parsed: list[ClosedM5V1] = []
    for raw in raw_rows:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 7:
            raise EventUniverseError("M5 row must preserve start/OHLC/base-volume/quote-turnover")
        start = _exact_int(raw[0], "kline start", nonnegative=True)
        if start % M5_INTERVAL_MS:
            raise EventUniverseError("M5 row start is not interval-aligned")
        # Forming and future rows are ignored before duplicate/gap checks so a
        # mutation to the open tail cannot change the causal score.
        if start + M5_INTERVAL_MS > as_of_ms:
            continue
        o = _finite_float(raw[1], "open", positive=True)
        h = _finite_float(raw[2], "high", positive=True)
        l = _finite_float(raw[3], "low", positive=True)
        c = _finite_float(raw[4], "close", positive=True)
        v = _finite_float(raw[5], "base volume", nonnegative=True)
        q = _finite_float(raw[6], "quote turnover", nonnegative=True)
        if h < max(o, l, c) or l > min(o, h, c):
            raise EventUniverseError("M5 OHLC geometry is invalid")
        parsed.append(ClosedM5V1(start, o, h, l, c, v, q))
    parsed.sort(key=lambda row: row.start_ms)
    if len({row.start_ms for row in parsed}) != len(parsed):
        raise EventUniverseError("duplicate M5 start timestamp")
    if len(parsed) < required_bars:
        raise EventUniverseError("not enough closed M5 rows")
    tail = parsed[-required_bars:]
    for previous, current in zip(tail, tail[1:]):
        if current.start_ms != previous.start_ms + M5_INTERVAL_MS:
            raise EventUniverseError("closed M5 tail is not contiguous")
    return tuple(tail)


@dataclass(frozen=True)
class EventScoreV1:
    symbol: str
    as_of_ms: int
    ok: bool
    reason: str
    heuristic_rank: float
    rank_semantics: str
    direction: str
    listing_tier: str
    recent_quote_usd: float
    baseline_quote_usd: float
    inflow_mult: float
    inflow_z: float
    recent_return_pct: float
    range_expansion_atr: float
    latest_body_fraction: float
    input_sha256: str
    candidate_id: str

    def payload(self) -> dict[str, Any]:
        return {"schema_id": SCORE_SCHEMA_ID, **dataclasses.asdict(self)}


def _true_ranges(rows: Sequence[ClosedM5V1]) -> list[float]:
    result: list[float] = []
    previous_close: float | None = None
    for row in rows:
        tr = row.high - row.low
        if previous_close is not None:
            tr = max(tr, abs(row.high - previous_close), abs(row.low - previous_close))
        result.append(tr)
        previous_close = row.close
    return result


def score_event_m5(
    symbol: str,
    raw_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    listing_tier: str,
    config: EventUniverseConfigV1,
) -> EventScoreV1:
    symbol = str(symbol).strip().upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        raise EventUniverseError("score symbol is invalid")
    if listing_tier not in {"normal", "fresh_shadow"}:
        raise EventUniverseError("listing tier is invalid")
    rows = closed_contiguous_m5(
        raw_rows,
        as_of_ms=as_of_ms,
        required_bars=config.required_closed_bars,
    )
    baseline = rows[: config.baseline_bars]
    recent = rows[config.baseline_bars :]
    baseline_values = [row.quote_turnover for row in baseline]
    recent_quote = sum(row.quote_turnover for row in recent)
    baseline_per_bar = median(baseline_values)
    baseline_recent = baseline_per_bar * config.recent_bars
    if baseline_recent <= 0:
        raise EventUniverseError("baseline quote turnover is invalid")
    inflow_mult = recent_quote / baseline_recent
    mad = median(abs(value - baseline_per_bar) for value in baseline_values)
    robust_sigma = 1.4826 * mad * math.sqrt(config.recent_bars)
    # A flat volume history must not create an astronomical z-score.
    robust_sigma = max(robust_sigma, 0.10 * baseline_recent, 1e-9)
    inflow_z = (recent_quote - baseline_recent) / robust_sigma
    pre_event_close = baseline[-1].close
    recent_return_pct = (recent[-1].close - pre_event_close) / pre_event_close * 100.0
    true_ranges = _true_ranges(baseline)
    prior_atr = median(true_ranges[-14:])
    if prior_atr <= 0:
        raise EventUniverseError("prior M5 ATR is invalid")
    event_range = max(row.high for row in recent) - min(row.low for row in recent)
    range_expansion = event_range / prior_atr
    latest = recent[-1]
    latest_range = latest.high - latest.low
    body_fraction = 0.0 if latest_range <= 0 else abs(latest.close - latest.open) / latest_range
    direction = "long" if recent_return_pct > 0 else "short" if recent_return_pct < 0 else "neutral"

    mult_component = min(1.0, max(0.0, (inflow_mult - 1.0) / max(config.min_inflow_mult, 1.0)))
    z_component = min(1.0, max(0.0, inflow_z / max(config.min_inflow_z * 3.0, 1.0)))
    range_component = min(1.0, max(0.0, range_expansion / max(config.min_range_expansion_atr * 3.0, 1.0)))
    liquidity_component = min(1.0, recent_quote / max(config.min_recent_quote_usd * 4.0, 1.0))
    move_component = min(1.0, abs(recent_return_pct) / 8.0)
    heuristic_rank = 100.0 * (
        0.30 * mult_component
        + 0.20 * z_component
        + 0.20 * range_component
        + 0.20 * liquidity_component
        + 0.10 * move_component
    )

    reason = "event_ok"
    ok = True
    if recent_quote < config.min_recent_quote_usd:
        ok, reason = False, "recent_quote_too_low"
    elif inflow_mult < config.min_inflow_mult:
        ok, reason = False, "inflow_mult_low"
    elif inflow_z < config.min_inflow_z:
        ok, reason = False, "inflow_z_low"
    elif abs(recent_return_pct) > config.max_abs_recent_return_pct:
        ok, reason = False, "recent_move_too_extreme"
    elif range_expansion < config.min_range_expansion_atr:
        ok, reason = False, "range_expansion_low"

    input_payload = [row.payload() for row in rows]
    input_sha = sha256_payload(input_payload)
    identity = {
        "schema_id": SCORE_SCHEMA_ID,
        "symbol": symbol,
        "as_of_ms": int(as_of_ms),
        "listing_tier": listing_tier,
        "config_sha256": config.config_sha256,
        "input_sha256": input_sha,
    }
    return EventScoreV1(
        symbol=symbol,
        as_of_ms=int(as_of_ms),
        ok=ok,
        reason=reason,
        heuristic_rank=round(heuristic_rank, 6),
        rank_semantics="heuristic_rank_not_probability",
        direction=direction,
        listing_tier=listing_tier,
        recent_quote_usd=round(recent_quote, 9),
        baseline_quote_usd=round(baseline_recent, 9),
        inflow_mult=round(inflow_mult, 9),
        inflow_z=round(inflow_z, 9),
        recent_return_pct=round(recent_return_pct, 9),
        range_expansion_atr=round(range_expansion, 9),
        latest_body_fraction=round(body_fraction, 9),
        input_sha256=input_sha,
        candidate_id=sha256_payload(identity),
    )


def build_snapshot_payload(
    *,
    as_of_ms: int,
    config: EventUniverseConfigV1,
    instruments_page_sha256: Sequence[str],
    tickers_sha256: str,
    market_rows: Sequence[MarketEligibilityV1],
    prefetch_symbols: Sequence[str],
    scores: Sequence[EventScoreV1],
    errors_by_symbol: Mapping[str, str],
    sequence: int,
    previous_snapshot_sha256: str | None,
) -> dict[str, Any]:
    """Build a self-hashing immutable prospective observation receipt."""
    as_of_ms = _exact_int(as_of_ms, "as_of_ms", positive=True)
    sequence = _exact_int(sequence, "sequence", positive=True)
    page_hashes = tuple(str(value) for value in instruments_page_sha256)
    if not page_hashes or any(len(value) != 64 for value in page_hashes):
        raise EventUniverseError("instrument page hashes are incomplete")
    if len(str(tickers_sha256)) != 64:
        raise EventUniverseError("ticker hash is incomplete")
    if previous_snapshot_sha256 is not None and len(previous_snapshot_sha256) != 64:
        raise EventUniverseError("previous snapshot hash is invalid")
    market_sorted = sorted(market_rows, key=lambda row: row.symbol)
    if len({row.symbol for row in market_sorted}) != len(market_sorted):
        raise EventUniverseError("duplicate market symbols")
    prefetch = tuple(prefetch_symbols)
    if len(prefetch) > config.max_prefetch_symbols or len(set(prefetch)) != len(prefetch):
        raise EventUniverseError("prefetch list is invalid")
    score_sorted = sorted(scores, key=lambda item: (-item.heuristic_rank, item.symbol))
    if len({item.symbol for item in score_sorted}) != len(score_sorted):
        raise EventUniverseError("duplicate scored symbols")
    if any(item.symbol not in set(prefetch) for item in score_sorted):
        raise EventUniverseError("score exists outside the frozen prefetch list")
    observations = [item.payload() for item in score_sorted[: config.top_k]]
    cards = [item.payload() for item in score_sorted if item.ok][: config.top_k]
    payload: dict[str, Any] = {
        "schema_id": SNAPSHOT_SCHEMA_ID,
        "source_id": SOURCE_ID,
        "research_only": True,
        "executable": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "performance_claims": False,
        "sequence": sequence,
        "as_of_ms": as_of_ms,
        "previous_snapshot_sha256": previous_snapshot_sha256,
        "config": dataclasses.asdict(config),
        "config_sha256": config.config_sha256,
        "source_receipts": {
            "instrument_page_sha256": list(page_hashes),
            "tickers_sha256": str(tickers_sha256),
        },
        "universe": [row.payload() for row in market_sorted],
        "universe_sha256": sha256_payload([row.payload() for row in market_sorted]),
        "prefetch_symbols": list(prefetch),
        "prefetch_count": len(prefetch),
        "scores": [item.payload() for item in score_sorted],
        "top_observations": observations,
        "top_cards": cards,
        "score_count": len(score_sorted),
        "event_candidate_count": sum(1 for item in score_sorted if item.ok),
        "errors_by_symbol": dict(sorted((str(k), str(v)) for k, v in errors_by_symbol.items())),
    }
    payload["snapshot_sha256"] = sha256_payload(payload)
    return payload


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_snapshot_payload(
    payload: Mapping[str, Any],
    *,
    config: EventUniverseConfigV1,
    require_replay: bool = False,
) -> None:
    """Validate checksum plus the semantic invariants bound by the snapshot."""
    if payload.get("schema_id") != SNAPSHOT_SCHEMA_ID:
        raise EventUniverseError("snapshot schema mismatch")
    if payload.get("source_id") != SOURCE_ID:
        raise EventUniverseError("snapshot source mismatch")
    frozen_authority = {
        "research_only": True,
        "executable": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "performance_claims": False,
    }
    if any(payload.get(key) is not expected for key, expected in frozen_authority.items()):
        raise EventUniverseError("snapshot research authority mismatch")
    if payload.get("config_sha256") != config.config_sha256:
        raise EventUniverseError("snapshot config hash mismatch")
    if payload.get("config") != dataclasses.asdict(config):
        raise EventUniverseError("snapshot embedded config mismatch")
    sequence = _exact_int(payload.get("sequence"), "snapshot sequence", positive=True)
    as_of_ms = _exact_int(payload.get("as_of_ms"), "snapshot as_of_ms", positive=True)
    previous = payload.get("previous_snapshot_sha256")
    if sequence == 1:
        if previous is not None:
            raise EventUniverseError("first snapshot must not have a previous hash")
    elif not _is_sha256(previous):
        raise EventUniverseError("snapshot previous hash is invalid")

    receipts = payload.get("source_receipts")
    if not isinstance(receipts, Mapping):
        raise EventUniverseError("snapshot source receipts are missing")
    page_hashes = receipts.get("instrument_page_sha256")
    if not isinstance(page_hashes, list) or not page_hashes or any(not _is_sha256(item) for item in page_hashes):
        raise EventUniverseError("snapshot instrument receipts are invalid")
    if not _is_sha256(receipts.get("tickers_sha256")):
        raise EventUniverseError("snapshot ticker receipt is invalid")
    kline_hashes = receipts.get("kline_sha256_by_symbol", {})
    if not isinstance(kline_hashes, Mapping) or any(
        not isinstance(symbol, str) or not _is_sha256(source_hash)
        for symbol, source_hash in kline_hashes.items()
    ):
        raise EventUniverseError("snapshot kline receipts are invalid")

    universe = payload.get("universe")
    if not isinstance(universe, list) or any(not isinstance(row, Mapping) for row in universe):
        raise EventUniverseError("snapshot universe is invalid")
    universe_symbols = [str(row.get("symbol") or "") for row in universe]
    if universe_symbols != sorted(universe_symbols) or len(set(universe_symbols)) != len(universe_symbols):
        raise EventUniverseError("snapshot universe ordering/identity is invalid")
    if any(row.get("schema_id") != MARKET_ROW_SCHEMA_ID for row in universe):
        raise EventUniverseError("snapshot universe row schema is invalid")
    if payload.get("universe_sha256") != sha256_payload(universe):
        raise EventUniverseError("snapshot universe checksum mismatch")

    prefetch = payload.get("prefetch_symbols")
    if not isinstance(prefetch, list) or len(prefetch) > config.max_prefetch_symbols:
        raise EventUniverseError("snapshot prefetch list is invalid")
    if len(set(prefetch)) != len(prefetch) or payload.get("prefetch_count") != len(prefetch):
        raise EventUniverseError("snapshot prefetch count/identity mismatch")
    eligible_symbols = {str(row.get("symbol")) for row in universe if row.get("eligible") is True}
    if any(symbol not in eligible_symbols for symbol in prefetch):
        raise EventUniverseError("snapshot prefetch symbol is not eligible")

    scores = payload.get("scores")
    if not isinstance(scores, list) or any(not isinstance(score, Mapping) for score in scores):
        raise EventUniverseError("snapshot scores are invalid")
    score_symbols = [str(score.get("symbol") or "") for score in scores]
    if len(set(score_symbols)) != len(score_symbols) or any(symbol not in set(prefetch) for symbol in score_symbols):
        raise EventUniverseError("snapshot score identity is invalid")
    if any(
        score.get("schema_id") != SCORE_SCHEMA_ID
        or score.get("as_of_ms") != as_of_ms
        or score.get("rank_semantics") != "heuristic_rank_not_probability"
        or not _is_sha256(score.get("input_sha256"))
        or not _is_sha256(score.get("candidate_id"))
        for score in scores
    ):
        raise EventUniverseError("snapshot score contract is invalid")
    expected_scores = sorted(scores, key=lambda item: (-float(item["heuristic_rank"]), str(item["symbol"])))
    if scores != expected_scores or payload.get("score_count") != len(scores):
        raise EventUniverseError("snapshot score ordering/count mismatch")
    candidates = [score for score in scores if score.get("ok") is True]
    if payload.get("event_candidate_count") != len(candidates):
        raise EventUniverseError("snapshot event candidate count mismatch")
    if payload.get("top_observations") != scores[: config.top_k]:
        raise EventUniverseError("snapshot top observations mismatch")
    if payload.get("top_cards") != candidates[: config.top_k]:
        raise EventUniverseError("snapshot candidate cards mismatch")
    errors = payload.get("errors_by_symbol")
    if not isinstance(errors, Mapping) or any(symbol not in set(prefetch) for symbol in errors):
        raise EventUniverseError("snapshot symbol errors are invalid")
    if set(errors) & set(score_symbols):
        raise EventUniverseError("snapshot symbol cannot be both scored and errored")
    if require_replay or "kline_sha256_by_symbol" in receipts:
        if not set(score_symbols).issubset(kline_hashes) or any(symbol not in set(prefetch) for symbol in kline_hashes):
            raise EventUniverseError("snapshot kline receipt coverage mismatch")

    replay = payload.get("replay_bundle")
    if require_replay and not isinstance(replay, Mapping):
        raise EventUniverseError("snapshot normalized replay bundle is required")
    if replay is not None:
        if not isinstance(replay, Mapping):
            raise EventUniverseError("snapshot replay metadata is invalid")
        required_replay = {
            "schema_id",
            "scope",
            "file",
            "compression",
            "compressed_sha256",
            "uncompressed_sha256",
            "compressed_bytes",
            "uncompressed_bytes",
            "symbol_count",
        }
        if set(replay) != required_replay:
            raise EventUniverseError("snapshot replay metadata fields mismatch")
        if (
            replay.get("schema_id") != "event_universe_normalized_replay_v1"
            or replay.get("scope") != "score_replay_delta_chain_source_hashes_asserted_not_replayed"
            or replay.get("compression") != "gzip"
        ):
            raise EventUniverseError("snapshot replay schema/compression mismatch")
        compressed_hash = replay.get("compressed_sha256")
        uncompressed_hash = replay.get("uncompressed_sha256")
        if not _is_sha256(compressed_hash) or not _is_sha256(uncompressed_hash):
            raise EventUniverseError("snapshot replay checksum is invalid")
        if replay.get("file") != f"replay_objects/{uncompressed_hash}.json.gz":
            raise EventUniverseError("snapshot replay filename is not content-addressed")
        if _exact_int(replay.get("compressed_bytes"), "replay compressed bytes", positive=True) > config.max_response_bytes:
            raise EventUniverseError("snapshot replay compressed byte cap exceeded")
        if _exact_int(replay.get("uncompressed_bytes"), "replay uncompressed bytes", positive=True) > config.max_replay_uncompressed_bytes:
            raise EventUniverseError("snapshot replay uncompressed byte cap exceeded")
        if _exact_int(replay.get("symbol_count"), "replay symbol count", positive=False) != len(scores):
            raise EventUniverseError("snapshot replay symbol count mismatch")

    expected = dict(payload)
    observed_hash = str(expected.pop("snapshot_sha256", ""))
    if not _is_sha256(observed_hash) or observed_hash != sha256_payload(expected):
        raise EventUniverseError("snapshot checksum mismatch")
