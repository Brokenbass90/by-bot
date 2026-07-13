"""Deterministic, fail-closed aggregation of canonical closed M5 bars.

This is research infrastructure only.  It does not fetch market data, place
orders, or make strategy decisions.  The caller must provide a complete UTC
M5 window containing only bars whose close is known at ``as_of_ms``.  Unlike a
convenience resampler, this contract never drops an open tail or fills a gap:
ambiguous evidence raises :class:`ClosedBarAggregationError`.

Provider identity (for example ``research`` or ``live``) is retained as
provenance but is deliberately excluded from bar bytes and bar/config hashes.
Consequently two paths using the same canonical input and provider fingerprint
produce identical aggregated bars and hashes.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from numbers import Integral
from typing import Any, Sequence, Tuple


AGGREGATION_SCHEMA = "closed_bar_aggregation_v1"
SOURCE_TIMEFRAME = "M5"
SOURCE_INTERVAL_MS = 300_000
TARGET_INTERVALS_MS = {
    "M15": 900_000,
    "H1": 3_600_000,
    "H4": 14_400_000,
}
_FLOAT_FORMAT = ".17g"
_ALGORITHM_ID = "utc_complete_children_ohlcv_v1"

CanonicalBarV1 = Tuple[int, float, float, float, float, float]


class ClosedBarAggregationError(ValueError):
    """Input cannot be aggregated without inventing or leaking evidence."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _strict_nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ClosedBarAggregationError(f"{field} must be an integer")
    if isinstance(value, Integral):
        result = int(value)
    elif isinstance(value, str) and value and value == value.strip() and value.isdigit():
        result = int(value)
    else:
        raise ClosedBarAggregationError(f"{field} must be an integer")
    if result < 0:
        raise ClosedBarAggregationError(f"{field} must be non-negative")
    return result


def _strict_float(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ClosedBarAggregationError(f"{field} must be numeric")
    if isinstance(value, str) and (not value or value != value.strip()):
        raise ClosedBarAggregationError(f"{field} must be canonical numeric text")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ClosedBarAggregationError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ClosedBarAggregationError(f"{field} must be finite")
    # There is only one canonical representation of zero in bar hashes.
    return 0.0 if result == 0.0 else result


def _normalise_bar(raw: Sequence[Any], *, row_number: int) -> CanonicalBarV1:
    if isinstance(raw, (str, bytes)):
        raise ClosedBarAggregationError(f"row {row_number} must contain exactly six fields")
    try:
        length = len(raw)
    except TypeError as exc:
        raise ClosedBarAggregationError(
            f"row {row_number} must contain exactly six fields"
        ) from exc
    if length != 6:
        raise ClosedBarAggregationError(f"row {row_number} must contain exactly six fields")

    ts = _strict_nonnegative_int(raw[0], field=f"row {row_number} open_ts_ms")
    o = _strict_float(raw[1], field=f"row {row_number} open")
    h = _strict_float(raw[2], field=f"row {row_number} high")
    low = _strict_float(raw[3], field=f"row {row_number} low")
    c = _strict_float(raw[4], field=f"row {row_number} close")
    v = _strict_float(raw[5], field=f"row {row_number} volume")

    if min(o, h, low, c) <= 0.0:
        raise ClosedBarAggregationError(f"row {row_number} prices must be positive")
    if v < 0.0:
        raise ClosedBarAggregationError(f"row {row_number} volume must be non-negative")
    if h < max(o, c) or low > min(o, c) or low > h:
        raise ClosedBarAggregationError(f"row {row_number} has invalid OHLC geometry")
    return (ts, o, h, low, c, v)


def _bar_payload(bars: Sequence[CanonicalBarV1]) -> list[list[object]]:
    return [
        [bar[0], *(format(value, _FLOAT_FORMAT) for value in bar[1:])]
        for bar in bars
    ]


def canonical_bars_bytes(bars: Sequence[Sequence[Any]]) -> bytes:
    """Return provider-independent canonical bytes for valid OHLCV bars."""

    normalised = tuple(
        _normalise_bar(row, row_number=index) for index, row in enumerate(bars)
    )
    return _canonical_json(_bar_payload(normalised))


def canonical_bars_sha256(bars: Sequence[Sequence[Any]]) -> str:
    """Hash canonical bar bytes after numeric normalisation and validation."""

    return hashlib.sha256(canonical_bars_bytes(bars)).hexdigest()


def _validate_provider_identity(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ClosedBarAggregationError("provider_identity must be a non-empty canonical string")
    if len(value) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ClosedBarAggregationError("provider_identity contains unsupported characters")
    return value


@dataclass(frozen=True)
class ClosedBarAggregationConfigV1:
    """Non-weakenable v1 aggregation contract."""

    target_timeframe: str
    source_timeframe: str = SOURCE_TIMEFRAME
    source_interval_ms: int = SOURCE_INTERVAL_MS
    require_utc_grid: bool = True
    require_contiguous_source: bool = True
    require_full_target_buckets: bool = True
    require_closed_source: bool = True

    def __post_init__(self) -> None:
        if self.target_timeframe not in TARGET_INTERVALS_MS:
            raise ClosedBarAggregationError("target_timeframe must be exactly M15, H1, or H4")
        if self.source_timeframe != SOURCE_TIMEFRAME:
            raise ClosedBarAggregationError("v1 source_timeframe must be exactly M5")
        if self.source_interval_ms != SOURCE_INTERVAL_MS:
            raise ClosedBarAggregationError("v1 source_interval_ms must be 300000")
        strict_fields = (
            "require_utc_grid",
            "require_contiguous_source",
            "require_full_target_buckets",
            "require_closed_source",
        )
        if any(getattr(self, field) is not True for field in strict_fields):
            raise ClosedBarAggregationError("v1 safety requirements cannot be disabled")

    @property
    def target_interval_ms(self) -> int:
        return TARGET_INTERVALS_MS[self.target_timeframe]

    @property
    def fingerprint(self) -> str:
        payload = {
            "schema": AGGREGATION_SCHEMA,
            "algorithm": _ALGORITHM_ID,
            "numeric_normalisation": f"binary64/{_FLOAT_FORMAT}",
            "source_timeframe": self.source_timeframe,
            "source_interval_ms": self.source_interval_ms,
            "target_timeframe": self.target_timeframe,
            "target_interval_ms": self.target_interval_ms,
            "require_utc_grid": self.require_utc_grid,
            "require_contiguous_source": self.require_contiguous_source,
            "require_full_target_buckets": self.require_full_target_buckets,
            "require_closed_source": self.require_closed_source,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


@dataclass(frozen=True)
class ClosedBarAggregationResultV1:
    """Immutable aggregate plus exact source and configuration provenance."""

    schema: str
    source_timeframe: str
    source_interval_ms: int
    target_timeframe: str
    target_interval_ms: int
    as_of_ms: int
    source_start_open_ts_ms: int
    source_end_close_ts_ms: int
    source_count: int
    source_sha256: str
    output_bars: Tuple[CanonicalBarV1, ...]
    output_count: int
    output_sha256: str
    provider_identity: str
    provider_fingerprint: str
    config_fingerprint: str

    def __post_init__(self) -> None:
        if self.schema != AGGREGATION_SCHEMA:
            raise ClosedBarAggregationError("aggregation result schema mismatch")
        cfg = ClosedBarAggregationConfigV1(target_timeframe=self.target_timeframe)
        if (
            self.source_timeframe != cfg.source_timeframe
            or self.source_interval_ms != cfg.source_interval_ms
            or self.target_interval_ms != cfg.target_interval_ms
        ):
            raise ClosedBarAggregationError("aggregation result interval mismatch")
        if self.config_fingerprint != cfg.fingerprint:
            raise ClosedBarAggregationError("aggregation result config fingerprint mismatch")
        _validate_provider_identity(self.provider_identity)
        if not _is_sha256(self.provider_fingerprint):
            raise ClosedBarAggregationError("provider_fingerprint must be lowercase SHA256")
        if not _is_sha256(self.source_sha256):
            raise ClosedBarAggregationError("source_sha256 must be lowercase SHA256")
        if not _is_sha256(self.output_sha256):
            raise ClosedBarAggregationError("output_sha256 must be lowercase SHA256")
        if not isinstance(self.output_bars, tuple) or not self.output_bars:
            raise ClosedBarAggregationError("output_bars must be a non-empty immutable tuple")
        if self.source_count <= 0 or self.output_count <= 0:
            raise ClosedBarAggregationError("source/output counts must be positive")
        children = self.target_interval_ms // self.source_interval_ms
        if self.source_count != self.output_count * children:
            raise ClosedBarAggregationError("source/output counts do not describe full buckets")
        if self.output_count != len(self.output_bars):
            raise ClosedBarAggregationError("output_count does not match output_bars")
        if self.source_start_open_ts_ms % self.target_interval_ms != 0:
            raise ClosedBarAggregationError("source window starts in a partial target bucket")
        if self.source_end_close_ts_ms % self.target_interval_ms != 0:
            raise ClosedBarAggregationError("source window ends in a partial target bucket")
        expected_span = self.source_count * self.source_interval_ms
        if self.source_end_close_ts_ms - self.source_start_open_ts_ms != expected_span:
            raise ClosedBarAggregationError("source window/count are inconsistent")
        if self.as_of_ms < self.source_end_close_ts_ms:
            raise ClosedBarAggregationError("source window is not fully closed at as_of_ms")

        previous_ts = None
        for index, raw in enumerate(self.output_bars):
            if not isinstance(raw, tuple):
                raise ClosedBarAggregationError("each output bar must be an immutable tuple")
            bar = _normalise_bar(raw, row_number=index)
            if bar != raw or not isinstance(raw[0], Integral) or isinstance(raw[0], bool):
                raise ClosedBarAggregationError("output bar is not in canonical representation")
            if bar[0] % self.target_interval_ms != 0:
                raise ClosedBarAggregationError("output bar is off the target UTC grid")
            if previous_ts is not None and bar[0] - previous_ts != self.target_interval_ms:
                raise ClosedBarAggregationError("output bars are not contiguous")
            previous_ts = bar[0]
        if self.output_bars[0][0] != self.source_start_open_ts_ms:
            raise ClosedBarAggregationError("first output bar does not match source window")
        if self.output_bars[-1][0] + self.target_interval_ms != self.source_end_close_ts_ms:
            raise ClosedBarAggregationError("last output bar does not match source window")
        if canonical_bars_sha256(self.output_bars) != self.output_sha256:
            raise ClosedBarAggregationError("output_sha256 does not match output_bars")

    def output_bytes(self) -> bytes:
        """Canonical provider-independent bytes of ``output_bars``."""

        return canonical_bars_bytes(self.output_bars)


def aggregate_closed_m5_bars(
    raw_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    provider_identity: str,
    provider_fingerprint: str,
    config: ClosedBarAggregationConfigV1,
) -> ClosedBarAggregationResultV1:
    """Aggregate a complete, contiguous closed M5 window to M15/H1/H4.

    ``raw_rows`` must start and end on complete target-bucket boundaries.  An
    expected open tail is still rejected: callers must explicitly pass only
    the evidence that was closed at ``as_of_ms``.
    """

    if not isinstance(config, ClosedBarAggregationConfigV1):
        raise ClosedBarAggregationError("config must be ClosedBarAggregationConfigV1")
    cutoff = _strict_nonnegative_int(as_of_ms, field="as_of_ms")
    identity = _validate_provider_identity(provider_identity)
    fingerprint = str(provider_fingerprint or "")
    if not _is_sha256(fingerprint):
        raise ClosedBarAggregationError("provider_fingerprint must be lowercase SHA256")
    if isinstance(raw_rows, (str, bytes)):
        raise ClosedBarAggregationError("raw_rows must be a non-empty sequence of bars")
    try:
        if len(raw_rows) == 0:
            raise ClosedBarAggregationError("raw_rows must not be empty")
    except TypeError as exc:
        raise ClosedBarAggregationError("raw_rows must be an inspectable sequence") from exc

    source: list[CanonicalBarV1] = []
    seen: set[int] = set()
    previous_ts: int | None = None
    for index, raw in enumerate(raw_rows):
        bar = _normalise_bar(raw, row_number=index)
        ts = bar[0]
        if ts % config.source_interval_ms != 0:
            raise ClosedBarAggregationError(f"row {index} is off the M5 UTC grid")
        if ts + config.source_interval_ms > cutoff:
            raise ClosedBarAggregationError(f"row {index} closes after as_of_ms")
        if ts in seen:
            raise ClosedBarAggregationError(f"row {index} duplicates a source timestamp")
        if previous_ts is not None and ts < previous_ts:
            raise ClosedBarAggregationError(f"row {index} is out of timestamp order")
        source.append(bar)
        seen.add(ts)
        previous_ts = ts

    for index in range(1, len(source)):
        if source[index][0] - source[index - 1][0] != config.source_interval_ms:
            raise ClosedBarAggregationError(
                f"row {index} reveals a missing M5 child or non-contiguous source"
            )

    target_ms = config.target_interval_ms
    children = target_ms // config.source_interval_ms
    source_start = source[0][0]
    source_end = source[-1][0] + config.source_interval_ms
    if source_start % target_ms != 0:
        raise ClosedBarAggregationError("source starts with a partial target bucket")
    if source_end % target_ms != 0 or len(source) % children != 0:
        raise ClosedBarAggregationError("source ends with a partial target bucket")

    output: list[CanonicalBarV1] = []
    for offset in range(0, len(source), children):
        bucket = source[offset : offset + children]
        if len(bucket) != children:
            raise ClosedBarAggregationError("target bucket is missing an M5 child")
        expected_start = source_start + (offset // children) * target_ms
        if bucket[0][0] != expected_start or bucket[-1][0] + config.source_interval_ms != expected_start + target_ms:
            raise ClosedBarAggregationError("target bucket is not complete on the UTC grid")
        volume = math.fsum(bar[5] for bar in bucket)
        if not math.isfinite(volume):
            raise ClosedBarAggregationError("aggregated volume is non-finite")
        output.append(
            (
                expected_start,
                bucket[0][1],
                max(bar[2] for bar in bucket),
                min(bar[3] for bar in bucket),
                bucket[-1][4],
                0.0 if volume == 0.0 else volume,
            )
        )

    output_tuple = tuple(output)
    return ClosedBarAggregationResultV1(
        schema=AGGREGATION_SCHEMA,
        source_timeframe=config.source_timeframe,
        source_interval_ms=config.source_interval_ms,
        target_timeframe=config.target_timeframe,
        target_interval_ms=target_ms,
        as_of_ms=cutoff,
        source_start_open_ts_ms=source_start,
        source_end_close_ts_ms=source_end,
        source_count=len(source),
        source_sha256=canonical_bars_sha256(source),
        output_bars=output_tuple,
        output_count=len(output_tuple),
        output_sha256=canonical_bars_sha256(output_tuple),
        provider_identity=identity,
        provider_fingerprint=fingerprint,
        config_fingerprint=config.fingerprint,
    )


__all__ = [
    "AGGREGATION_SCHEMA",
    "SOURCE_INTERVAL_MS",
    "SOURCE_TIMEFRAME",
    "TARGET_INTERVALS_MS",
    "CanonicalBarV1",
    "ClosedBarAggregationConfigV1",
    "ClosedBarAggregationError",
    "ClosedBarAggregationResultV1",
    "aggregate_closed_m5_bars",
    "canonical_bars_bytes",
    "canonical_bars_sha256",
]
