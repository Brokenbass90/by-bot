"""Causal, fail-closed OHLCV store for mutable-prefix research replays.

The strategy corpus uses the live ``fetch_klines(symbol, timeframe, limit)``
shape.  A research replay advances one closed source bar at a time by replacing
``rows`` with the causal prefix.  This store never substitutes the source
timeframe for a requested one and never exposes an incomplete higher-timeframe
bar.
"""

from __future__ import annotations

from collections import Counter
import math
from numbers import Integral
import re
from typing import Sequence


class ResearchKlineStoreError(ValueError):
    """The requested market-data view cannot be produced without ambiguity."""


def timeframe_minutes(value: object) -> int:
    """Normalize fixed-duration Bybit/common timeframe spellings to minutes."""

    if isinstance(value, bool):
        raise ResearchKlineStoreError("timeframe must be a positive fixed duration")
    if isinstance(value, Integral):
        minutes = int(value)
        if minutes > 0:
            return minutes
        raise ResearchKlineStoreError("timeframe must be a positive fixed duration")
    if not isinstance(value, str) or not value or value != value.strip():
        raise ResearchKlineStoreError("timeframe must be canonical text or integer minutes")

    if value.isdigit():
        minutes = int(value)
        if minutes > 0:
            return minutes
        raise ResearchKlineStoreError("timeframe must be a positive fixed duration")

    # Upper-case M is conventionally a calendar month on exchanges.  A month
    # is not a fixed-duration UTC bucket, so silently treating 1M as one minute
    # would corrupt evidence.
    if value == "M" or value.endswith("M"):
        raise ResearchKlineStoreError("calendar-month timeframe is not supported")

    match = re.fullmatch(r"(?i)([mhdw])(\d+)", value)
    if match:
        unit, count = match.group(1).lower(), int(match.group(2))
    else:
        match = re.fullmatch(r"(?i)(\d+)([mhdw])", value)
        if not match:
            raise ResearchKlineStoreError(f"unsupported timeframe: {value}")
        count, unit = int(match.group(1)), match.group(2).lower()
    if count <= 0:
        raise ResearchKlineStoreError("timeframe must be a positive fixed duration")
    return count * {"m": 1, "h": 60, "d": 1440, "w": 10080}[unit]


def _normalise_row(raw: Sequence[object], *, row_number: int) -> list[float | int]:
    if isinstance(raw, (str, bytes)) or len(raw) < 6:
        raise ResearchKlineStoreError(f"row {row_number} must contain at least six fields")
    try:
        ts = int(raw[0])
        o, high, low, close, volume = (float(raw[index]) for index in range(1, 6))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchKlineStoreError(f"row {row_number} contains non-numeric OHLCV") from exc
    if ts < 0 or any(not math.isfinite(value) for value in (o, high, low, close, volume)):
        raise ResearchKlineStoreError(f"row {row_number} contains non-finite OHLCV")
    if min(o, high, low, close) <= 0 or volume < 0:
        raise ResearchKlineStoreError(f"row {row_number} contains invalid prices or volume")
    if high < max(o, close) or low > min(o, close) or low > high:
        raise ResearchKlineStoreError(f"row {row_number} has invalid OHLC geometry")
    return [ts, o, high, low, close, volume]


class ResearchKlineStore:
    """Per-symbol causal kline store whose ``rows`` are closed source bars."""

    def __init__(self, symbol: str, base_interval_minutes: int | None = None):
        if not isinstance(symbol, str) or not symbol.strip():
            raise ResearchKlineStoreError("symbol must be non-empty text")
        self.symbol = symbol.strip()
        self.rows: list[Sequence[object]] = []
        self._base_interval_minutes = (
            timeframe_minutes(base_interval_minutes)
            if base_interval_minutes is not None
            else None
        )
        self.contract_errors: Counter[str] = Counter()

    def _error(self, reason: str, message: str) -> ResearchKlineStoreError:
        self.contract_errors[reason] += 1
        return ResearchKlineStoreError(message)

    @property
    def base_interval_minutes(self) -> int:
        if self._base_interval_minutes is not None:
            return self._base_interval_minutes
        if len(self.rows) < 2:
            raise self._error(
                "source_timeframe_unknown",
                "at least two source rows are required to infer the source timeframe",
            )
        timestamps = [int(row[0]) for row in self.rows[: min(len(self.rows), 65)]]
        deltas = [right - left for left, right in zip(timestamps, timestamps[1:]) if right > left]
        if not deltas:
            raise self._error("source_timeframe_unknown", "source timestamps do not advance")
        deltas.sort()
        inferred_ms = deltas[len(deltas) // 2]
        if inferred_ms % 60_000:
            raise self._error("source_off_grid", "source timeframe is not an integer minute")
        self._base_interval_minutes = inferred_ms // 60_000
        return self._base_interval_minutes

    def fetch_klines(self, symbol: str, timeframe: object, limit: int):
        if symbol != self.symbol:
            raise self._error("wrong_symbol", "ResearchKlineStore is per-symbol")
        if isinstance(limit, bool) or not isinstance(limit, Integral) or int(limit) < 0:
            raise self._error("invalid_limit", "limit must be a non-negative integer")
        requested = int(limit)
        if requested == 0 or not self.rows:
            return []

        try:
            target_minutes = timeframe_minutes(timeframe)
        except ResearchKlineStoreError as exc:
            raise self._error("unsupported_timeframe", str(exc)) from exc
        base_minutes = self.base_interval_minutes
        if target_minutes < base_minutes:
            raise self._error(
                "finer_than_source",
                f"requested timeframe {target_minutes}m is finer than source {base_minutes}m",
            )
        if target_minutes % base_minutes:
            raise self._error(
                "non_integral_timeframe",
                f"requested timeframe {target_minutes}m is not divisible by source {base_minutes}m",
            )

        if target_minutes == base_minutes:
            # Validate exactly the evidence returned to the strategy.
            result = list(self.rows[-requested:])
            normalised = [_normalise_row(row, row_number=index) for index, row in enumerate(result)]
            base_ms = base_minutes * 60_000
            for index, row in enumerate(normalised):
                if row[0] % base_ms:
                    raise self._error("source_off_grid", f"row {index} is off the source UTC grid")
                if index and row[0] - normalised[index - 1][0] != base_ms:
                    raise self._error("missing_source_child", "missing source child in requested window")
            return result

        base_ms = base_minutes * 60_000
        target_ms = target_minutes * 60_000
        children = target_minutes // base_minutes
        # One extra target bucket lets us discard a partial leading bucket
        # caused only by tail slicing while still returning ``limit`` results.
        raw_tail = list(self.rows[-(requested + 1) * children :])
        source = [_normalise_row(row, row_number=index) for index, row in enumerate(raw_tail)]
        for index, row in enumerate(source):
            if row[0] % base_ms:
                raise self._error("source_off_grid", f"row {index} is off the source UTC grid")
            if index and row[0] <= source[index - 1][0]:
                raise self._error("source_order", "source timestamps must be strictly increasing")

        current_source_end = source[-1][0] + base_ms
        complete_end = (current_source_end // target_ms) * target_ms
        first_ts = source[0][0]
        first_full_start = ((first_ts + target_ms - 1) // target_ms) * target_ms
        if first_ts % target_ms == 0:
            first_full_start = first_ts

        by_timestamp = {int(row[0]): row for row in source}
        output: list[list[float | int]] = []
        for bucket_start in range(first_full_start, complete_end, target_ms):
            expected = [bucket_start + offset * base_ms for offset in range(children)]
            missing = [timestamp for timestamp in expected if timestamp not in by_timestamp]
            if missing:
                raise self._error(
                    "missing_source_child",
                    f"missing source child in complete {target_minutes}m bucket",
                )
            bucket = [by_timestamp[timestamp] for timestamp in expected]
            output.append(
                [
                    bucket_start,
                    bucket[0][1],
                    max(row[2] for row in bucket),
                    min(row[3] for row in bucket),
                    bucket[-1][4],
                    math.fsum(row[5] for row in bucket),
                ]
            )
        return output[-requested:]


# Preserve the short public name used throughout existing research scripts.
Store = ResearchKlineStore
