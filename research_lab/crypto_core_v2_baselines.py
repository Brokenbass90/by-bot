"""Offline parity adapters for the two explicitly frozen crypto baselines.

This module deliberately adds no signal, filter, trend, cost, or outcome logic.
The native strategy result is carried as ``data`` so callers can inspect the
original decision and rejection evidence without an adapter reinterpretation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Optional, Sequence

from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy
from strategies.event_expansion_retest_long_v1 import (
    EventExpansionRetestLongV1Research,
    ExpansionRetestLongConfig,
    config_sha256,
)


BASELINE_RESEARCH_REF = "cf904086a2d887a96ac2be3324a3d78433e1a94b"
BASELINE_SOURCE_PINS: Mapping[str, str] = {
    "event_expansion_retest_long_v1": "e50c4f1a0610c03e6ed79a9bc06023f14a12dcfa",
    "alt_support_bounce_v1": "b8fcdca3974161ddc1804384fd1dd5bb28168857",
}


@dataclass(frozen=True)
class ClosedBarAvailability:
    status: str
    as_of_ms: Optional[int] = None
    observed_last_bar_ms: Optional[int] = None
    source_periods: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostAssumptions:
    status: str = "UNKNOWN_BLOCKED"
    fee_bps: Optional[float] = None
    slippage_bps: Optional[float] = None
    funding_bps: Optional[float] = None
    source_sha256: str = ""
    unknowns: tuple[str, ...] = (
        "fee_schedule",
        "slippage_model",
        "funding_treatment",
    )

    def __post_init__(self) -> None:
        for value in (self.fee_bps, self.slippage_bps, self.funding_bps):
            if value is not None and (not math.isfinite(float(value)) or float(value) < 0):
                raise ValueError("cost assumptions must be finite and non-negative")
        if self.status == "CONFIRMED" and (
            any(value is None for value in (self.fee_bps, self.slippage_bps, self.funding_bps))
            or self.unknowns or len(self.source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.source_sha256)
        ):
            raise ValueError("confirmed costs require complete source-bound values and resolved unknowns")


@dataclass(frozen=True)
class OpportunityRecord:
    family: str
    strategy: str
    symbol: str
    decision: str
    side: str
    data: str
    native_sha256: str
    reason: str
    availability: ClosedBarAvailability
    costs: CostAssumptions
    source_ref: str = BASELINE_RESEARCH_REF
    source_blob: str = ""
    config_sha256: str = ""

    def native_copy(self) -> Any:
        """Return a detached JSON value; the receipt itself remains immutable."""
        return json.loads(self.data)


def _native_json(native: Any) -> tuple[str, str]:
    payload = asdict(native) if hasattr(native, "__dataclass_fields__") else native
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record(
    *, family: str, strategy: str, symbol: str, decision: str, data: Any,
    reason: str, availability: ClosedBarAvailability,
    costs: Optional[CostAssumptions] = None,
    config_fingerprint: str = "",
) -> OpportunityRecord:
    native_json, native_sha = _native_json(data) if data is not None else ("null", hashlib.sha256(b"null").hexdigest())
    return OpportunityRecord(
        family=family,
        strategy=strategy,
        symbol=str(symbol).upper(),
        decision=decision,
        side="long",
        data=native_json,
        native_sha256=native_sha,
        reason=reason,
        availability=availability,
        costs=costs or CostAssumptions(),
        source_blob=BASELINE_SOURCE_PINS[family],
        config_sha256=config_fingerprint,
    )


def _blocked(*, family: str, strategy: str, symbol: str, as_of_ms: Optional[int], last_ms: Optional[int]) -> OpportunityRecord:
    return _record(
        family=family,
        strategy=strategy,
        symbol=symbol,
        decision="blocked",
        data=None,
        reason="BLOCKED_DATA:closed_bar_availability_unknown",
        availability=ClosedBarAvailability(
            status="BLOCKED_DATA", as_of_ms=as_of_ms,
            observed_last_bar_ms=last_ms,
            unknowns=("closed_bar_availability",),
        ),
    )


def _closed_rows_proven(rows: Sequence[Sequence[Any]], *, as_of_ms: Optional[int], interval_ms: int) -> tuple[bool, Optional[int]]:
    if as_of_ms is None:
        return False, None
    last_ms: Optional[int] = None
    try:
        for row in rows:
            ts = int(float(row[0]))
            if ts < 0 or ts + interval_ms > int(as_of_ms):
                return False, ts
            last_ms = ts
    except (IndexError, TypeError, ValueError, OverflowError):
        return False, last_ms
    return True, last_ms


def adapt_event_expansion_retest(
    symbol: str,
    rows: Sequence[Sequence[Any]],
    level_snapshots: Sequence[Any],
    *,
    cfg: Optional[ExpansionRetestLongConfig] = None,
    as_of_ms: Optional[int] = None,
    research: Optional[EventExpansionRetestLongV1Research] = None,
    costs: Optional[CostAssumptions] = None,
) -> OpportunityRecord:
    """Call the frozen event baseline and normalize its native step result."""
    config = cfg or ExpansionRetestLongConfig()
    closed, last_ms = _closed_rows_proven(rows, as_of_ms=as_of_ms, interval_ms=config.interval_ms)
    if research is not None and research.cfg != config:
        raise ValueError("event research config is not pinned")
    if not closed:
        return _blocked(
            family="event_expansion_retest_long_v1",
            strategy="event_expansion_retest_long_v1",
            symbol=symbol,
            as_of_ms=as_of_ms,
            last_ms=last_ms,
        )
    runner = research or EventExpansionRetestLongV1Research(config)
    native = runner.process_closed_rows(
        str(symbol).upper(), rows, level_snapshots
    )
    accepted = native.plan is not None
    return _record(
        family="event_expansion_retest_long_v1",
        strategy="event_expansion_retest_long_v1",
        symbol=symbol,
        decision="accepted" if accepted else "rejected",
        data=native,
        reason=native.reason,
        availability=ClosedBarAvailability(
            status="CLOSED_BAR_CONFIRMED", as_of_ms=int(as_of_ms),
            observed_last_bar_ms=last_ms, source_periods=("M5", "H1", "H4"),
        ),
        config_fingerprint=config_sha256(config),
        costs=costs,
    )


def adapt_alt_support_bounce(
    strategy: AltSupportBounceV1Strategy,
    store: Any,
    ts_ms: int,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float = 0.0,
    *,
    as_of_ms: Optional[int] = None,
    source_rows: Optional[Mapping[str, Sequence[Sequence[Any]]]] = None,
    closed_bar_available: Optional[bool] = None,
    costs: Optional[CostAssumptions] = None,
) -> OpportunityRecord:
    """Call the frozen bounce baseline only after explicit closed-bar proof."""
    symbol = str(getattr(store, "symbol", "")).upper()
    # Only the immutable rows whose closing times were validated can reach the
    # native store interface. The supplied backing store contributes identity,
    # never an independent, possibly live/unclosed, fetch.
    aliases = {"60": "1h", "1h": "1h", "240": "4h", "4h": "4h"}
    required = (aliases.get(str(strategy.cfg.signal_tf)), aliases.get(str(strategy.cfg.regime_tf)))
    intervals = {"1h": 3_600_000, "4h": 14_400_000}
    frozen_rows = json.loads(json.dumps(source_rows, allow_nan=False)) if source_rows is not None else None
    proven = (all(required) and frozen_rows is not None and as_of_ms is not None
              and 0 <= int(ts_ms) <= int(as_of_ms) and all(
        period in frozen_rows and _closed_rows_proven(
            frozen_rows[period], as_of_ms=as_of_ms, interval_ms=intervals[period]
        )[0]
        for period in required
    ))
    if not proven:
        return _blocked(
            family="alt_support_bounce_v1", strategy="alt_support_bounce_v1",
            symbol=symbol, as_of_ms=as_of_ms, last_ms=None,
        )
    class FrozenStore:
        def __init__(self): self.symbol = symbol
        def fetch_klines(self, requested_symbol, timeframe, limit):
            period = aliases.get(str(timeframe))
            if str(requested_symbol).upper() != symbol or period not in required:
                raise ValueError("unvalidated native source request")
            return [list(row) for row in frozen_rows[period][-limit:]]
    native = strategy.maybe_signal(FrozenStore(), ts_ms, o, h, l, c, v)
    reason = "signal_emitted" if native is not None else strategy.last_no_signal_reason
    return _record(
        family="alt_support_bounce_v1", strategy="alt_support_bounce_v1",
        symbol=symbol, decision="accepted" if native is not None else "rejected",
        data=native, reason=reason,
        availability=ClosedBarAvailability(
            status="CLOSED_BAR_CONFIRMED", as_of_ms=int(as_of_ms),
            observed_last_bar_ms=max((int(float(row[0])) for period in required
                                     for row in frozen_rows[period]), default=None),
            source_periods=tuple(sorted(set(required))),
        ),
        config_fingerprint=_native_json({"config":asdict(strategy.cfg),
            "symbol_allowlist":sorted(strategy._allow), "symbol_denylist":sorted(strategy._deny)})[1],
        costs=costs,
    )


class CryptoCoreV2Adapter:
    """Family allowlist only; no generic dispatch or research policy."""

    def __init__(self, family: str):
        if family not in BASELINE_SOURCE_PINS:
            raise ValueError("unsupported crypto baseline family")
        self.family = family


__all__ = [
    "BASELINE_RESEARCH_REF", "BASELINE_SOURCE_PINS", "ClosedBarAvailability",
    "CostAssumptions", "OpportunityRecord", "CryptoCoreV2Adapter",
    "adapt_event_expansion_retest", "adapt_alt_support_bounce",
]
