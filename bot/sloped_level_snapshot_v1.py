"""Causal, immutable sloped-level evidence for offline research.

This module turns an already-supplied OHLCV prefix into one versioned support
or resistance line.  It is deliberately *not* a signal generator: there is no
market-data fetcher, live wiring, order placement, risk policy, performance
claim, candidate search, or parameter grid here.

The contract is intentionally stricter than :func:`bot.market_context.sloped_level`:

* only bars closed at ``as_of_ms`` enter the fit or hashes;
* every pivot is confirmed only after ``pivot_right`` later bars have closed;
* two points can never qualify (v1 requires at least three confirmed pivots);
* the fitted line must remain unbroken on closed-bar closes through ``as_of``;
* ``line_id`` binds the version/config/pivots while ``snapshot_id`` binds the
  exact closed input prefix and observation time;
* every non-accepted outcome carries an explicit, fail-closed reason.

Rows use the repository's canonical format
``[open_ts_ms, open, high, low, close, volume]``.  Future/forming tail rows may
be present, but cannot influence the fit, identities, or projection.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from numbers import Integral
from typing import Any, Optional, Sequence, Tuple

from bot.closed_bar_aggregation_v1 import (
    ClosedBarAggregationError,
    canonical_bars_sha256,
)
from bot.market_context import fit_line, pivot_highs, pivot_lows


SLOPED_LEVEL_SNAPSHOT_SCHEMA = "sloped_level_snapshot_v1"
SLOPED_LEVEL_BUILD_RESULT_SCHEMA = "sloped_level_build_result_v1"
ALLOWED_SIDES = {"support", "resistance"}
ALLOWED_STATUSES = {"accepted", "rejected"}
ACCEPTED_REASON = "accepted"
REJECTION_REASONS = {
    "invalid_config",
    "invalid_symbol",
    "invalid_side",
    "invalid_interval",
    "invalid_as_of",
    "invalid_source",
    "insufficient_closed_bars",
    "insufficient_confirmed_pivots",
    "degenerate_fit",
    "fit_quality_below_minimum",
    "line_broken",
    "projection_invalid",
}
_FLOAT_FORMAT = ".17g"
TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


class SlopedLevelSnapshotError(ValueError):
    """Configuration or materialised snapshot violates the v1 contract."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _is_id32(value: object) -> bool:
    text = str(value or "")
    return len(text) == 32 and all(char in "0123456789abcdef" for char in text)


def _strict_nonnegative_int(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        result = int(value)
    elif isinstance(value, str) and value and value == value.strip() and value.isdigit():
        result = int(value)
    else:
        return None
    return result if result >= 0 else None


@dataclass(frozen=True)
class SlopedLevelConfigV1:
    """Frozen geometry contract, not an optimisation/search specification."""

    lookback_bars: int = 240
    pivot_left: int = 2
    pivot_right: int = 2
    min_confirmed_pivots: int = 3
    min_r_squared: float = 0.80
    require_contiguous_source: bool = True
    require_unbroken_closes: bool = True

    def __post_init__(self) -> None:
        for field in (
            "lookback_bars",
            "pivot_left",
            "pivot_right",
            "min_confirmed_pivots",
        ):
            value = getattr(self, field)
            if not isinstance(value, Integral) or isinstance(value, bool) or value <= 0:
                raise SlopedLevelSnapshotError(f"{field} must be a positive integer")
        if self.min_confirmed_pivots < 3:
            raise SlopedLevelSnapshotError(
                "v1 requires at least three confirmed pivots; two-point R2 is not evidence"
            )
        minimum_window = self.pivot_left + self.pivot_right + self.min_confirmed_pivots
        if self.lookback_bars < minimum_window:
            raise SlopedLevelSnapshotError("lookback_bars cannot confirm the required pivots")
        if (
            not math.isfinite(float(self.min_r_squared))
            or not 0.0 <= float(self.min_r_squared) <= 1.0
        ):
            raise SlopedLevelSnapshotError("min_r_squared must be within [0, 1]")
        if self.require_contiguous_source is not True:
            raise SlopedLevelSnapshotError("v1 contiguous-source safety cannot be disabled")
        if self.require_unbroken_closes is not True:
            raise SlopedLevelSnapshotError("v1 unbroken-close safety cannot be disabled")

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "schema": SLOPED_LEVEL_SNAPSHOT_SCHEMA,
                "algorithm": "all_confirmed_prefix_pivots_ols_close_unbroken_v1",
                "lookback_bars": int(self.lookback_bars),
                "pivot_left": int(self.pivot_left),
                "pivot_right": int(self.pivot_right),
                "min_confirmed_pivots": int(self.min_confirmed_pivots),
                "min_r_squared": format(float(self.min_r_squared), _FLOAT_FORMAT),
                "require_contiguous_source": self.require_contiguous_source,
                "require_unbroken_closes": self.require_unbroken_closes,
            }
        )


@dataclass(frozen=True)
class ConfirmedSlopedPivotV1:
    pivot_ts_ms: int
    confirmed_at_ms: int
    price: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.pivot_ts_ms, Integral)
            or isinstance(self.pivot_ts_ms, bool)
            or not isinstance(self.confirmed_at_ms, Integral)
            or isinstance(self.confirmed_at_ms, bool)
            or self.pivot_ts_ms < 0
            or self.confirmed_at_ms <= self.pivot_ts_ms
        ):
            raise SlopedLevelSnapshotError("pivot confirmation timeline is invalid")
        if not math.isfinite(float(self.price)) or float(self.price) <= 0.0:
            raise SlopedLevelSnapshotError("pivot price must be finite and positive")


def _pivots_payload(pivots: Sequence[ConfirmedSlopedPivotV1]) -> list[list[object]]:
    return [
        [
            int(pivot.pivot_ts_ms),
            int(pivot.confirmed_at_ms),
            format(float(pivot.price), _FLOAT_FORMAT),
        ]
        for pivot in pivots
    ]


def _line_identity_payload(
    *,
    symbol: str,
    interval_ms: int,
    side: str,
    config_sha256: str,
    pivots: Sequence[ConfirmedSlopedPivotV1],
) -> dict[str, Any]:
    return {
        "schema": SLOPED_LEVEL_SNAPSHOT_SCHEMA,
        "symbol": symbol,
        "interval_ms": interval_ms,
        "side": side,
        "break_basis": "closed_bar_close",
        "config_sha256": config_sha256,
        "pivots": _pivots_payload(pivots),
    }


@dataclass(frozen=True)
class SlopedLevelSnapshotV1:
    schema: str
    line_id: str
    snapshot_id: str
    symbol: str
    interval_ms: int
    side: str
    as_of_ms: int
    source_start_ts_ms: int
    source_end_close_ms: int
    source_count: int
    source_sha256: str
    config_sha256: str
    input_sha256: str
    pivots_sha256: str
    confirmed_pivots: Tuple[ConfirmedSlopedPivotV1, ...]
    anchor_ts_ms: int
    intercept_at_anchor: float
    slope_per_interval: float
    r_squared: float
    projected_at_as_of: float
    break_basis: str
    unbroken_through_ms: int
    payload_sha256: str

    def __post_init__(self) -> None:
        if self.schema != SLOPED_LEVEL_SNAPSHOT_SCHEMA:
            raise SlopedLevelSnapshotError("snapshot schema mismatch")
        if not (_is_id32(self.line_id) and _is_id32(self.snapshot_id)):
            raise SlopedLevelSnapshotError("snapshot identities must be lowercase 32-hex")
        if not all(
            _is_sha256(value)
            for value in (
                self.source_sha256,
                self.config_sha256,
                self.input_sha256,
                self.pivots_sha256,
                self.payload_sha256,
            )
        ):
            raise SlopedLevelSnapshotError("snapshot hashes must be lowercase SHA256")
        if self.side not in ALLOWED_SIDES or self.break_basis != "closed_bar_close":
            raise SlopedLevelSnapshotError("snapshot side/break basis is invalid")
        if not self.symbol or self.symbol != self.symbol.strip().upper():
            raise SlopedLevelSnapshotError("symbol must be canonical uppercase")
        if len(self.confirmed_pivots) < 3:
            raise SlopedLevelSnapshotError("snapshot requires at least three confirmed pivots")
        for field in (
            "interval_ms",
            "as_of_ms",
            "source_start_ts_ms",
            "source_end_close_ms",
            "source_count",
            "anchor_ts_ms",
            "unbroken_through_ms",
        ):
            value = getattr(self, field)
            if not isinstance(value, Integral) or isinstance(value, bool):
                raise SlopedLevelSnapshotError(f"{field} must be a canonical integer")
        if (
            self.interval_ms <= 0
            or self.source_count <= 0
            or self.source_start_ts_ms < 0
            or self.source_end_close_ms > self.as_of_ms
            or self.unbroken_through_ms != self.source_end_close_ms
            or self.anchor_ts_ms != self.confirmed_pivots[0].pivot_ts_ms
        ):
            raise SlopedLevelSnapshotError("snapshot source timeline is invalid")
        if tuple(sorted(self.confirmed_pivots, key=lambda item: item.pivot_ts_ms)) != self.confirmed_pivots:
            raise SlopedLevelSnapshotError("confirmed pivots must be ordered")
        if any(pivot.confirmed_at_ms > self.as_of_ms for pivot in self.confirmed_pivots):
            raise SlopedLevelSnapshotError("snapshot contains an unconfirmed pivot")
        numeric = (
            self.intercept_at_anchor,
            self.slope_per_interval,
            self.r_squared,
            self.projected_at_as_of,
        )
        if not all(math.isfinite(float(value)) for value in numeric):
            raise SlopedLevelSnapshotError("snapshot line contains non-finite values")
        if (
            self.intercept_at_anchor <= 0.0
            or self.projected_at_as_of <= 0.0
            or not 0.0 <= self.r_squared <= 1.0
            or abs(self.slope_per_interval) <= max(
                1e-12, abs(self.intercept_at_anchor) * 1e-12
            )
        ):
            raise SlopedLevelSnapshotError("snapshot line geometry is invalid")

        pivots_sha = _sha256(_pivots_payload(self.confirmed_pivots))
        if pivots_sha != self.pivots_sha256:
            raise SlopedLevelSnapshotError("pivot evidence hash mismatch")
        expected_line_id = _sha256(
            _line_identity_payload(
                symbol=self.symbol,
                interval_ms=self.interval_ms,
                side=self.side,
                config_sha256=self.config_sha256,
                pivots=self.confirmed_pivots,
            )
        )[:32]
        if expected_line_id != self.line_id:
            raise SlopedLevelSnapshotError("line identity mismatch")

        payload = _snapshot_payload(self, include_payload_sha=False)
        if _sha256(payload) != self.payload_sha256:
            raise SlopedLevelSnapshotError("snapshot payload hash mismatch")


def _snapshot_payload(
    snapshot: SlopedLevelSnapshotV1,
    *,
    include_payload_sha: bool,
) -> dict[str, Any]:
    payload = _snapshot_payload_from_values(
        {field: getattr(snapshot, field) for field in snapshot.__dataclass_fields__}
    )
    if include_payload_sha:
        payload["payload_sha256"] = snapshot.payload_sha256
    return payload


def _snapshot_payload_from_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": values["schema"],
        "line_id": values["line_id"],
        "snapshot_id": values["snapshot_id"],
        "symbol": values["symbol"],
        "interval_ms": values["interval_ms"],
        "side": values["side"],
        "as_of_ms": values["as_of_ms"],
        "source_start_ts_ms": values["source_start_ts_ms"],
        "source_end_close_ms": values["source_end_close_ms"],
        "source_count": values["source_count"],
        "source_sha256": values["source_sha256"],
        "config_sha256": values["config_sha256"],
        "input_sha256": values["input_sha256"],
        "pivots_sha256": values["pivots_sha256"],
        "confirmed_pivots": _pivots_payload(values["confirmed_pivots"]),
        "anchor_ts_ms": values["anchor_ts_ms"],
        "intercept_at_anchor": format(values["intercept_at_anchor"], _FLOAT_FORMAT),
        "slope_per_interval": format(values["slope_per_interval"], _FLOAT_FORMAT),
        "r_squared": format(values["r_squared"], _FLOAT_FORMAT),
        "projected_at_as_of": format(values["projected_at_as_of"], _FLOAT_FORMAT),
        "break_basis": values["break_basis"],
        "unbroken_through_ms": values["unbroken_through_ms"],
    }


@dataclass(frozen=True)
class SlopedLevelBuildResultV1:
    """Explicit accepted/rejected receipt; rejected always means no line."""

    schema: str
    status: str
    reason: str
    side: str
    as_of_ms: Optional[int]
    closed_bars: int
    confirmed_pivots: int
    input_sha256: Optional[str]
    snapshot: Optional[SlopedLevelSnapshotV1]

    def __post_init__(self) -> None:
        if self.schema != SLOPED_LEVEL_BUILD_RESULT_SCHEMA:
            raise SlopedLevelSnapshotError("build-result schema mismatch")
        if self.status not in ALLOWED_STATUSES:
            raise SlopedLevelSnapshotError("invalid build-result status")
        if self.closed_bars < 0 or self.confirmed_pivots < 0:
            raise SlopedLevelSnapshotError("build-result counts cannot be negative")
        if self.status == "accepted":
            if self.reason != ACCEPTED_REASON or self.snapshot is None:
                raise SlopedLevelSnapshotError("accepted result must contain a snapshot")
            if self.input_sha256 != self.snapshot.input_sha256:
                raise SlopedLevelSnapshotError("accepted result input hash mismatch")
        elif self.reason not in REJECTION_REASONS or self.snapshot is not None:
            raise SlopedLevelSnapshotError("rejected result must be fail-closed with a reason")
        if self.input_sha256 is not None and not _is_sha256(self.input_sha256):
            raise SlopedLevelSnapshotError("build-result input hash must be lowercase SHA256")


def _rejected(
    reason: str,
    *,
    side: str,
    as_of_ms: Optional[int],
    closed_bars: int = 0,
    confirmed_pivots: int = 0,
    input_sha256: Optional[str] = None,
) -> SlopedLevelBuildResultV1:
    return SlopedLevelBuildResultV1(
        schema=SLOPED_LEVEL_BUILD_RESULT_SCHEMA,
        status="rejected",
        reason=reason,
        side=side,
        as_of_ms=as_of_ms,
        closed_bars=closed_bars,
        confirmed_pivots=confirmed_pivots,
        input_sha256=input_sha256,
        snapshot=None,
    )


def _closed_prefix(
    raw_rows: Sequence[Sequence[Any]],
    *,
    interval_ms: int,
    as_of_ms: int,
    lookback_bars: int,
) -> Tuple[Tuple[int, float, float, float, float, float], ...]:
    closed: list[Tuple[int, float, float, float, float, float]] = []
    previous_ts = -1
    for row_number, raw in enumerate(raw_rows):
        if isinstance(raw, (str, bytes)):
            raise SlopedLevelSnapshotError("source row is not OHLCV")
        try:
            if len(raw) != 6:
                raise SlopedLevelSnapshotError("source row must contain exactly six fields")
        except TypeError as exc:
            raise SlopedLevelSnapshotError("source row must contain exactly six fields") from exc
        ts = _strict_nonnegative_int(raw[TS])
        if ts is None or ts % interval_ms != 0 or ts <= previous_ts:
            raise SlopedLevelSnapshotError("source timestamps must be ordered on the interval grid")
        previous_ts = ts
        if ts + interval_ms > as_of_ms:
            # A forming/future tail is timestamp-validated but otherwise opaque;
            # its prices must not enter causal validation, fitting, or hashing.
            continue
        try:
            canonical_bars_sha256([raw])
            values = tuple(float(raw[index]) for index in (OPEN, HIGH, LOW, CLOSE, VOL))
        except (ClosedBarAggregationError, TypeError, ValueError, OverflowError) as exc:
            raise SlopedLevelSnapshotError(
                f"closed source row {row_number} is not canonical OHLCV"
            ) from exc
        closed.append((ts, *values))

    window = tuple(closed[-int(lookback_bars) :])
    if any(
        int(window[index][TS]) - int(window[index - 1][TS]) != interval_ms
        for index in range(1, len(window))
    ):
        raise SlopedLevelSnapshotError("closed research window is not contiguous")
    return window


def build_sloped_level_snapshot_v1(
    symbol: str,
    side: str,
    interval_ms: int,
    raw_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    cfg: Optional[SlopedLevelConfigV1] = None,
) -> SlopedLevelBuildResultV1:
    """Materialise one causal line or return an explicit fail-closed receipt."""

    try:
        config = cfg or SlopedLevelConfigV1()
    except SlopedLevelSnapshotError:
        return _rejected("invalid_config", side=str(side or ""), as_of_ms=None)
    if not isinstance(config, SlopedLevelConfigV1):
        return _rejected("invalid_config", side=str(side or ""), as_of_ms=None)

    canonical_symbol = str(symbol or "").strip()
    if not canonical_symbol or canonical_symbol != canonical_symbol.upper():
        return _rejected("invalid_symbol", side=str(side or ""), as_of_ms=None)
    canonical_side = str(side or "").strip().lower()
    if canonical_side not in ALLOWED_SIDES:
        return _rejected("invalid_side", side=canonical_side, as_of_ms=None)
    interval = _strict_nonnegative_int(interval_ms)
    if interval is None or interval <= 0:
        return _rejected("invalid_interval", side=canonical_side, as_of_ms=None)
    observation_ms = _strict_nonnegative_int(as_of_ms)
    if observation_ms is None:
        return _rejected("invalid_as_of", side=canonical_side, as_of_ms=None)
    if isinstance(raw_rows, (str, bytes)):
        return _rejected("invalid_source", side=canonical_side, as_of_ms=observation_ms)

    try:
        window = _closed_prefix(
            raw_rows,
            interval_ms=interval,
            as_of_ms=observation_ms,
            lookback_bars=int(config.lookback_bars),
        )
    except (SlopedLevelSnapshotError, TypeError):
        return _rejected("invalid_source", side=canonical_side, as_of_ms=observation_ms)

    minimum_bars = int(config.pivot_left + config.pivot_right + config.min_confirmed_pivots)
    if len(window) < minimum_bars:
        return _rejected(
            "insufficient_closed_bars",
            side=canonical_side,
            as_of_ms=observation_ms,
            closed_bars=len(window),
        )

    source_sha = canonical_bars_sha256(window)
    config_sha = config.fingerprint
    raw_pivots = (
        pivot_lows(list(window), left=config.pivot_left, right=config.pivot_right)
        if canonical_side == "support"
        else pivot_highs(list(window), left=config.pivot_left, right=config.pivot_right)
    )
    pivots = tuple(
        ConfirmedSlopedPivotV1(
            pivot_ts_ms=int(item["ts"]),
            confirmed_at_ms=int(window[int(item["idx"]) + config.pivot_right][TS]) + interval,
            price=float(item["price"]),
        )
        for item in raw_pivots
    )
    input_payload = {
        "schema": SLOPED_LEVEL_SNAPSHOT_SCHEMA,
        "symbol": canonical_symbol,
        "side": canonical_side,
        "interval_ms": interval,
        "as_of_ms": observation_ms,
        "source_start_ts_ms": int(window[0][TS]),
        "source_end_close_ms": int(window[-1][TS]) + interval,
        "source_count": len(window),
        "source_sha256": source_sha,
        "config_sha256": config_sha,
        "pivots": _pivots_payload(pivots),
    }
    input_sha = _sha256(input_payload)
    if len(pivots) < int(config.min_confirmed_pivots):
        return _rejected(
            "insufficient_confirmed_pivots",
            side=canonical_side,
            as_of_ms=observation_ms,
            closed_bars=len(window),
            confirmed_pivots=len(pivots),
            input_sha256=input_sha,
        )

    anchor_ts = int(pivots[0].pivot_ts_ms)
    points = [
        ((pivot.pivot_ts_ms - anchor_ts) / float(interval), float(pivot.price))
        for pivot in pivots
    ]
    slope, intercept, r_squared = fit_line(points)
    minimum_slope = max(1e-12, abs(float(intercept)) * 1e-12) if math.isfinite(intercept) else 1e-12
    if (
        not all(math.isfinite(value) for value in (slope, intercept, r_squared))
        or abs(float(slope)) <= minimum_slope
    ):
        return _rejected(
            "degenerate_fit",
            side=canonical_side,
            as_of_ms=observation_ms,
            closed_bars=len(window),
            confirmed_pivots=len(pivots),
            input_sha256=input_sha,
        )
    if r_squared < float(config.min_r_squared):
        return _rejected(
            "fit_quality_below_minimum",
            side=canonical_side,
            as_of_ms=observation_ms,
            closed_bars=len(window),
            confirmed_pivots=len(pivots),
            input_sha256=input_sha,
        )

    first_pivot_index = next(
        index for index, row in enumerate(window) if int(row[TS]) == anchor_ts
    )
    broken = False
    for row in window[first_pivot_index:]:
        x = (int(row[TS]) - anchor_ts) / float(interval)
        line_value = float(slope) * x + float(intercept)
        epsilon = max(1e-12, abs(line_value) * 1e-12)
        close = float(row[CLOSE])
        if (
            canonical_side == "support" and close < line_value - epsilon
        ) or (
            canonical_side == "resistance" and close > line_value + epsilon
        ):
            broken = True
            break
    if broken:
        return _rejected(
            "line_broken",
            side=canonical_side,
            as_of_ms=observation_ms,
            closed_bars=len(window),
            confirmed_pivots=len(pivots),
            input_sha256=input_sha,
        )

    projection_x = (observation_ms - anchor_ts) / float(interval)
    projection = float(slope) * projection_x + float(intercept)
    if not math.isfinite(projection) or projection <= 0.0:
        return _rejected(
            "projection_invalid",
            side=canonical_side,
            as_of_ms=observation_ms,
            closed_bars=len(window),
            confirmed_pivots=len(pivots),
            input_sha256=input_sha,
        )

    pivots_sha = _sha256(_pivots_payload(pivots))
    line_id = _sha256(
        _line_identity_payload(
            symbol=canonical_symbol,
            interval_ms=interval,
            side=canonical_side,
            config_sha256=config_sha,
            pivots=pivots,
        )
    )[:32]
    snapshot_id = input_sha[:32]
    values = {
        "schema": SLOPED_LEVEL_SNAPSHOT_SCHEMA,
        "line_id": line_id,
        "snapshot_id": snapshot_id,
        "symbol": canonical_symbol,
        "interval_ms": interval,
        "side": canonical_side,
        "as_of_ms": observation_ms,
        "source_start_ts_ms": int(window[0][TS]),
        "source_end_close_ms": int(window[-1][TS]) + interval,
        "source_count": len(window),
        "source_sha256": source_sha,
        "config_sha256": config_sha,
        "input_sha256": input_sha,
        "pivots_sha256": pivots_sha,
        "confirmed_pivots": pivots,
        "anchor_ts_ms": anchor_ts,
        "intercept_at_anchor": float(intercept),
        "slope_per_interval": float(slope),
        "r_squared": float(r_squared),
        "projected_at_as_of": float(projection),
        "break_basis": "closed_bar_close",
        "unbroken_through_ms": int(window[-1][TS]) + interval,
    }
    payload_sha = _sha256(_snapshot_payload_from_values(values))
    snapshot = SlopedLevelSnapshotV1(**values, payload_sha256=payload_sha)
    return SlopedLevelBuildResultV1(
        schema=SLOPED_LEVEL_BUILD_RESULT_SCHEMA,
        status="accepted",
        reason=ACCEPTED_REASON,
        side=canonical_side,
        as_of_ms=observation_ms,
        closed_bars=len(window),
        confirmed_pivots=len(pivots),
        input_sha256=input_sha,
        snapshot=snapshot,
    )


__all__ = [
    "ACCEPTED_REASON",
    "ConfirmedSlopedPivotV1",
    "SLOPED_LEVEL_BUILD_RESULT_SCHEMA",
    "SLOPED_LEVEL_SNAPSHOT_SCHEMA",
    "SlopedLevelBuildResultV1",
    "SlopedLevelConfigV1",
    "SlopedLevelSnapshotError",
    "SlopedLevelSnapshotV1",
    "build_sloped_level_snapshot_v1",
]
