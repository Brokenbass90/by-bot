"""Immutable, causal higher-timeframe level contract (schema v1).

``unified_levels`` is useful for an on-demand chart, but a research event must
not silently redraw the level that caused it.  This module materialises one
horizontal H1/H4 resistance from *closed* source bars and gives it a stable
identity.  A breakout may return a new immutable view of the same level as
flipped support; a later failure may return an invalidated view.  Neither
transition changes ``level_id`` or the frozen source evidence.

The module is deliberately research infrastructure only.  It has no market
data fetcher, strategy router, broker adapter, performance runner, or risk
logic.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Optional, Sequence, Tuple

from bot.market_context import atr, cluster_levels, pivot_highs


LEVEL_SNAPSHOT_SCHEMA = "level_snapshot_v1"
ALLOWED_TIMEFRAMES = {"H1": 3_600_000, "H4": 14_400_000}
ALLOWED_LIFECYCLES = {"resistance", "flip_support", "invalidated"}
TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


class LevelSnapshotError(ValueError):
    """The supplied level evidence is ambiguous or causally unsafe."""


def _finite_positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _normalise_timeframe(value: str) -> tuple[str, int]:
    text = str(value or "").strip().upper()
    aliases = {"60": "H1", "1H": "H1", "240": "H4", "4H": "H4"}
    text = aliases.get(text, text)
    if text not in ALLOWED_TIMEFRAMES:
        raise LevelSnapshotError("timeframe must be H1 or H4")
    return text, ALLOWED_TIMEFRAMES[text]


@dataclass(frozen=True)
class ConfirmedPivotV1:
    pivot_ts_ms: int
    confirmed_at_ms: int
    price: float

    def __post_init__(self) -> None:
        if self.pivot_ts_ms < 0 or self.confirmed_at_ms <= self.pivot_ts_ms:
            raise LevelSnapshotError("pivot confirmation must follow the pivot")
        if not _finite_positive(self.price):
            raise LevelSnapshotError("pivot price must be finite and positive")


@dataclass(frozen=True)
class LevelRespectV1:
    """A confirmed rejection belonging to the frozen resistance history."""

    touch_ts_ms: int
    resolved_at_ms: int
    outcome: str
    approach: str
    touch_price: float
    reaction_close: float
    move_away_atr: float

    def __post_init__(self) -> None:
        if self.resolved_at_ms <= self.touch_ts_ms:
            raise LevelSnapshotError("respect resolution must follow its touch")
        if self.outcome != "resistance_rejection" or self.approach != "from_below":
            raise LevelSnapshotError("v1 history accepts only resistance rejections from below")
        if not (_finite_positive(self.touch_price) and _finite_positive(self.reaction_close)):
            raise LevelSnapshotError("respect prices must be finite and positive")
        if not math.isfinite(float(self.move_away_atr)) or self.move_away_atr < 0:
            raise LevelSnapshotError("move_away_atr must be finite and non-negative")


def _frozen_payload_from_parts(
    *, schema: str, level_id: str, symbol: str, timeframe: str, interval_ms: int,
    kind: str, zone_low: float, level: float, zone_high: float,
    atr_at_creation: float, confirmed_pivots: Tuple[ConfirmedPivotV1, ...],
    respect_history: Tuple[LevelRespectV1, ...], created_at_ms: int,
    valid_at_ms: int, source_start_ts_ms: int, source_end_close_ms: int,
    source_bars_sha256: str, provider_fingerprint: str, config_sha256: str,
) -> dict[str, Any]:
    """Canonical immutable evidence; lifecycle transitions are excluded."""
    return {
        "schema": schema,
        "level_id": level_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "interval_ms": interval_ms,
        "kind": kind,
        "zone": [format(zone_low, ".15g"), format(level, ".15g"), format(zone_high, ".15g")],
        "atr_at_creation": format(atr_at_creation, ".15g"),
        "pivots": [item.__dict__ for item in confirmed_pivots],
        "respects": [item.__dict__ for item in respect_history],
        "created_at_ms": created_at_ms,
        "valid_at_ms": valid_at_ms,
        "source_start_ts_ms": source_start_ts_ms,
        "source_end_close_ms": source_end_close_ms,
        "source_bars_sha256": source_bars_sha256,
        "provider_fingerprint": provider_fingerprint,
        "config_sha256": config_sha256,
    }


@dataclass(frozen=True)
class LevelSnapshotV1:
    schema: str
    level_id: str
    snapshot_id: str
    symbol: str
    timeframe: str
    interval_ms: int
    kind: str
    lifecycle: str
    zone_low: float
    level: float
    zone_high: float
    atr_at_creation: float
    confirmed_pivots: Tuple[ConfirmedPivotV1, ...]
    respect_history: Tuple[LevelRespectV1, ...]
    created_at_ms: int
    valid_at_ms: int
    source_start_ts_ms: int
    source_end_close_ms: int
    source_bars_sha256: str
    provider_fingerprint: str
    config_sha256: str
    payload_sha256: str
    flipped_at_ms: Optional[int] = None
    invalidated_at_ms: Optional[int] = None
    invalidation_reason: str = ""

    def __post_init__(self) -> None:
        if self.schema != LEVEL_SNAPSHOT_SCHEMA:
            raise LevelSnapshotError("level snapshot schema mismatch")
        if len(self.level_id) != 32 or any(c not in "0123456789abcdef" for c in self.level_id):
            raise LevelSnapshotError("level_id must be a 32-character lowercase hex identity")
        if len(self.snapshot_id) != 32 or any(c not in "0123456789abcdef" for c in self.snapshot_id):
            raise LevelSnapshotError("snapshot_id must be a 32-character lowercase hex identity")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise LevelSnapshotError("symbol must be canonical uppercase")
        timeframe, expected_interval = _normalise_timeframe(self.timeframe)
        if timeframe != self.timeframe or self.interval_ms != expected_interval:
            raise LevelSnapshotError("timeframe/interval mismatch")
        if self.kind != "horizontal_resistance":
            raise LevelSnapshotError("v1 supports horizontal resistance only")
        if self.lifecycle not in ALLOWED_LIFECYCLES:
            raise LevelSnapshotError("invalid level lifecycle")
        if not all(
            _finite_positive(value)
            for value in (self.zone_low, self.level, self.zone_high, self.atr_at_creation)
        ) or not self.zone_low < self.level < self.zone_high:
            raise LevelSnapshotError("invalid level-zone geometry")
        if len(self.confirmed_pivots) < 2 or len(self.respect_history) < 2:
            raise LevelSnapshotError("level needs at least two confirmed pivots/respects")
        pivot_times = tuple(item.pivot_ts_ms for item in self.confirmed_pivots)
        respect_times = tuple(item.touch_ts_ms for item in self.respect_history)
        if pivot_times != tuple(sorted(set(pivot_times))):
            raise LevelSnapshotError("confirmed pivots must be unique and ordered")
        if respect_times != tuple(sorted(set(respect_times))):
            raise LevelSnapshotError("respect history must be unique and ordered")
        if any(item.confirmed_at_ms > self.valid_at_ms for item in self.confirmed_pivots):
            raise LevelSnapshotError("snapshot predates a pivot confirmation")
        if any(item.resolved_at_ms > self.valid_at_ms for item in self.respect_history):
            raise LevelSnapshotError("snapshot predates a respect resolution")
        if not (
            0 <= self.source_start_ts_ms < self.source_end_close_ms
            <= self.created_at_ms
        ):
            raise LevelSnapshotError("invalid source/creation timeline")
        if not (self.valid_at_ms <= self.source_end_close_ms <= self.created_at_ms):
            raise LevelSnapshotError("snapshot is not valid on its frozen source timeline")
        if not all(
            _is_sha256(value)
            for value in (
                self.source_bars_sha256,
                self.provider_fingerprint,
                self.config_sha256,
                self.payload_sha256,
            )
        ):
            raise LevelSnapshotError("source/provider/config/payload fingerprints must be lowercase SHA256")
        expected_level_id = _stable_level_id(
            symbol=self.symbol,
            timeframe=self.timeframe,
            pivots=self.confirmed_pivots,
        )
        if self.level_id != expected_level_id:
            raise LevelSnapshotError("level_id does not match frozen pivot identity")
        frozen_payload = _frozen_payload_from_parts(
            schema=self.schema, level_id=self.level_id, symbol=self.symbol,
            timeframe=self.timeframe, interval_ms=self.interval_ms, kind=self.kind,
            zone_low=self.zone_low, level=self.level, zone_high=self.zone_high,
            atr_at_creation=self.atr_at_creation,
            confirmed_pivots=self.confirmed_pivots,
            respect_history=self.respect_history, created_at_ms=self.created_at_ms,
            valid_at_ms=self.valid_at_ms, source_start_ts_ms=self.source_start_ts_ms,
            source_end_close_ms=self.source_end_close_ms,
            source_bars_sha256=self.source_bars_sha256,
            provider_fingerprint=self.provider_fingerprint,
            config_sha256=self.config_sha256,
        )
        expected_payload_sha = hashlib.sha256(_canonical_json(frozen_payload)).hexdigest()
        if self.payload_sha256 != expected_payload_sha or self.snapshot_id != expected_payload_sha[:32]:
            raise LevelSnapshotError("snapshot/payload identity does not match frozen evidence")
        if self.lifecycle == "resistance":
            if self.flipped_at_ms is not None or self.invalidated_at_ms is not None:
                raise LevelSnapshotError("unflipped resistance has transition timestamps")
            if self.invalidation_reason:
                raise LevelSnapshotError("active resistance has invalidation reason")
        elif self.lifecycle == "flip_support":
            if self.flipped_at_ms is None or self.flipped_at_ms < self.valid_at_ms:
                raise LevelSnapshotError("flipped support is missing a causal flip timestamp")
            if self.invalidated_at_ms is not None or self.invalidation_reason:
                raise LevelSnapshotError("active flip cannot already be invalidated")
        else:
            if (
                self.flipped_at_ms is None
                or self.invalidated_at_ms is None
                or self.invalidated_at_ms <= self.flipped_at_ms
                or not self.invalidation_reason
            ):
                raise LevelSnapshotError("invalidated flip has incomplete lifecycle evidence")


@dataclass(frozen=True)
class LevelSnapshotConfigV1:
    lookback_bars: int = 240
    atr_period: int = 14
    pivot_left: int = 2
    pivot_right: int = 2
    min_confirmed_pivots: int = 2
    cluster_tolerance_atr: float = 0.30
    zone_half_width_atr: float = 0.18
    max_distance_atr: float = 3.0
    require_contiguous_source: bool = True

    def __post_init__(self) -> None:
        for name in (
            "lookback_bars", "atr_period", "pivot_left", "pivot_right",
            "min_confirmed_pivots",
        ):
            if int(getattr(self, name)) <= 0:
                raise LevelSnapshotError(f"{name} must be positive")
        if self.lookback_bars < self.atr_period + self.pivot_left + self.pivot_right + 3:
            raise LevelSnapshotError("lookback_bars is too short for ATR/pivot confirmation")
        if self.min_confirmed_pivots < 2:
            raise LevelSnapshotError("v1 level identity needs at least two confirmed pivots")
        for name in ("cluster_tolerance_atr", "zone_half_width_atr", "max_distance_atr"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise LevelSnapshotError(f"{name} must be finite and positive")


def _closed_source_rows(
    raw_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    interval_ms: int,
) -> list[list[float]]:
    """Validate all eligible bars and exclude only the expected open tail."""
    closed: list[list[float]] = []
    seen: set[int] = set()
    previous_ts = -1
    for raw in raw_rows:
        try:
            ts = int(float(raw[TS]))
        except (IndexError, TypeError, ValueError) as exc:
            raise LevelSnapshotError("source contains an invalid timestamp") from exc
        if ts + interval_ms > int(as_of_ms):
            continue
        if ts % interval_ms != 0:
            raise LevelSnapshotError("higher-timeframe timestamp is off its UTC grid")
        if ts in seen or ts <= previous_ts:
            raise LevelSnapshotError("closed source timestamps are duplicate or unordered")
        try:
            o, h, l, c, v = (float(raw[index]) for index in (OPEN, HIGH, LOW, CLOSE, VOL))
        except (IndexError, TypeError, ValueError) as exc:
            raise LevelSnapshotError("closed source contains malformed OHLCV") from exc
        if not all(math.isfinite(value) for value in (o, h, l, c, v)):
            raise LevelSnapshotError("closed source contains non-finite OHLCV")
        if (
            ts < 0
            or min(o, h, l, c) <= 0
            or v < 0
            or h < max(o, c, l)
            or l > min(o, c, h)
        ):
            raise LevelSnapshotError("closed source contains invalid OHLCV geometry")
        closed.append([float(ts), o, h, l, c, v])
        seen.add(ts)
        previous_ts = ts
    return closed


def source_bars_sha256(rows: Sequence[Sequence[Any]]) -> str:
    canonical = [
        [int(float(row[TS]))] + [format(float(row[index]), ".15g") for index in range(1, 6)]
        for row in rows
    ]
    return hashlib.sha256(_canonical_json(canonical)).hexdigest()


def _stable_level_id(
    *,
    symbol: str,
    timeframe: str,
    pivots: Tuple[ConfirmedPivotV1, ...],
) -> str:
    identity = {
        "schema": LEVEL_SNAPSHOT_SCHEMA,
        "symbol": symbol,
        "timeframe": timeframe,
        "kind": "horizontal_resistance",
        "pivots": [[item.pivot_ts_ms, format(item.price, ".12g")] for item in pivots],
    }
    return hashlib.sha256(_canonical_json(identity)).hexdigest()[:32]


def build_resistance_snapshot_v1(
    symbol: str,
    timeframe: str,
    raw_rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    provider_fingerprint: str,
    cfg: Optional[LevelSnapshotConfigV1] = None,
) -> Optional[LevelSnapshotV1]:
    """Build the nearest unbroken pre-event horizontal resistance.

    ``None`` means no qualifying level.  Ambiguous or corrupt input raises
    :class:`LevelSnapshotError`; callers must not convert that into an empty
    state and continue.
    """
    config = cfg or LevelSnapshotConfigV1()
    canonical_symbol = str(symbol or "").strip().upper()
    if not canonical_symbol or canonical_symbol != str(symbol or "").strip():
        raise LevelSnapshotError("symbol must already be canonical uppercase")
    canonical_tf, interval_ms = _normalise_timeframe(timeframe)
    provider_sha = str(provider_fingerprint or "").lower()
    if not _is_sha256(provider_sha):
        raise LevelSnapshotError("provider_fingerprint must be lowercase SHA256")
    rows = _closed_source_rows(raw_rows, as_of_ms=int(as_of_ms), interval_ms=interval_ms)
    need = max(
        config.atr_period + config.pivot_left + config.pivot_right + 3,
        2 * config.min_confirmed_pivots + config.pivot_right + 1,
    )
    if len(rows) < need:
        return None
    window = rows[-max(need, int(config.lookback_bars)) :]
    if config.require_contiguous_source and any(
        int(window[index][TS]) - int(window[index - 1][TS]) != interval_ms
        for index in range(1, len(window))
    ):
        raise LevelSnapshotError("source window contains a higher-timeframe gap")
    a = atr(window, config.atr_period)
    if not _finite_positive(a):
        return None
    pivots = pivot_highs(window, config.pivot_left, config.pivot_right)
    clusters = cluster_levels(pivots, max(1e-12, config.cluster_tolerance_atr * a))
    current_close = float(window[-1][CLOSE])
    candidates: list[dict[str, Any]] = []
    for cluster in clusters:
        if int(cluster["touches"]) < int(config.min_confirmed_pivots):
            continue
        center = float(cluster["level"])
        half_width = max(1e-12, float(config.zone_half_width_atr) * a)
        zone_low, zone_high = center - half_width, center + half_width
        # The event has not happened yet: current price must still be below the
        # resistance zone and close enough for a later explicit breakout.
        if current_close > zone_high or center - current_close > config.max_distance_atr * a:
            continue
        candidates.append(
            {
                "cluster": cluster,
                "center": center,
                "zone_low": zone_low,
                "zone_high": zone_high,
            }
        )
    if not candidates:
        return None
    chosen = min(
        candidates,
        key=lambda item: (abs(item["center"] - current_close), -int(item["cluster"]["touches"])),
    )
    cluster = chosen["cluster"]
    index_by_ts = {int(row[TS]): index for index, row in enumerate(window)}
    confirmed: list[ConfirmedPivotV1] = []
    respects: list[LevelRespectV1] = []
    for pivot_ts, pivot_price in sorted(zip(cluster["ts"], cluster["prices"])):
        pivot_ts = int(pivot_ts)
        pivot_index = index_by_ts[pivot_ts]
        confirmed_at = pivot_ts + (int(config.pivot_right) + 1) * interval_ms
        reaction_index = pivot_index + int(config.pivot_right)
        if reaction_index >= len(window) or confirmed_at > int(as_of_ms):
            raise LevelSnapshotError("cluster contains an unconfirmed pivot")
        reaction = window[reaction_index]
        move_away = max(
            0.0,
            (float(chosen["center"]) - min(float(row[LOW]) for row in window[pivot_index + 1 : reaction_index + 1]))
            / a,
        )
        confirmed.append(ConfirmedPivotV1(pivot_ts, confirmed_at, float(pivot_price)))
        respects.append(
            LevelRespectV1(
                touch_ts_ms=pivot_ts,
                resolved_at_ms=confirmed_at,
                outcome="resistance_rejection",
                approach="from_below",
                touch_price=float(pivot_price),
                reaction_close=float(reaction[CLOSE]),
                move_away_atr=move_away,
            )
        )
    confirmed_tuple = tuple(confirmed)
    respect_tuple = tuple(respects)
    valid_at = max(
        max(item.confirmed_at_ms for item in confirmed_tuple),
        max(item.resolved_at_ms for item in respect_tuple),
    )
    source_sha = source_bars_sha256(window)
    config_sha = hashlib.sha256(_canonical_json(asdict(config))).hexdigest()
    stable_id = _stable_level_id(
        symbol=canonical_symbol,
        timeframe=canonical_tf,
        pivots=confirmed_tuple,
    )
    frozen_payload = _frozen_payload_from_parts(
        schema=LEVEL_SNAPSHOT_SCHEMA, level_id=stable_id,
        symbol=canonical_symbol, timeframe=canonical_tf, interval_ms=interval_ms,
        kind="horizontal_resistance", zone_low=float(chosen["zone_low"]),
        level=float(chosen["center"]), zone_high=float(chosen["zone_high"]),
        atr_at_creation=float(a), confirmed_pivots=confirmed_tuple,
        respect_history=respect_tuple, created_at_ms=int(as_of_ms),
        valid_at_ms=int(valid_at), source_start_ts_ms=int(window[0][TS]),
        source_end_close_ms=int(window[-1][TS]) + interval_ms,
        source_bars_sha256=source_sha, provider_fingerprint=provider_sha,
        config_sha256=config_sha,
    )
    payload_sha = hashlib.sha256(_canonical_json(frozen_payload)).hexdigest()
    return LevelSnapshotV1(
        schema=LEVEL_SNAPSHOT_SCHEMA,
        level_id=stable_id,
        snapshot_id=payload_sha[:32],
        symbol=canonical_symbol,
        timeframe=canonical_tf,
        interval_ms=interval_ms,
        kind="horizontal_resistance",
        lifecycle="resistance",
        zone_low=float(chosen["zone_low"]),
        level=float(chosen["center"]),
        zone_high=float(chosen["zone_high"]),
        atr_at_creation=float(a),
        confirmed_pivots=confirmed_tuple,
        respect_history=respect_tuple,
        created_at_ms=int(as_of_ms),
        valid_at_ms=int(valid_at),
        source_start_ts_ms=int(window[0][TS]),
        source_end_close_ms=int(window[-1][TS]) + interval_ms,
        source_bars_sha256=source_sha,
        provider_fingerprint=provider_sha,
        config_sha256=config_sha,
        payload_sha256=payload_sha,
    )


def flip_level_snapshot_v1(
    snapshot: LevelSnapshotV1,
    *,
    breakout_ts_ms: int,
    breakout_close: float,
) -> LevelSnapshotV1:
    if snapshot.lifecycle != "resistance":
        raise LevelSnapshotError("only active resistance may flip")
    if int(breakout_ts_ms) < snapshot.created_at_ms:
        raise LevelSnapshotError("breakout predates the frozen snapshot")
    if not _finite_positive(breakout_close) or float(breakout_close) <= snapshot.zone_high:
        raise LevelSnapshotError("breakout close did not clear the frozen zone")
    return replace(
        snapshot,
        lifecycle="flip_support",
        flipped_at_ms=int(breakout_ts_ms),
    )


def invalidate_level_snapshot_v1(
    snapshot: LevelSnapshotV1,
    *,
    invalidated_at_ms: int,
    close: float,
    reason: str,
) -> LevelSnapshotV1:
    if snapshot.lifecycle != "flip_support" or snapshot.flipped_at_ms is None:
        raise LevelSnapshotError("only active flipped support may invalidate")
    if int(invalidated_at_ms) <= snapshot.flipped_at_ms:
        raise LevelSnapshotError("invalidation must follow the flip")
    if not _finite_positive(close) or float(close) >= snapshot.zone_low:
        raise LevelSnapshotError("invalidation close did not fail the frozen zone")
    if not str(reason or "").strip():
        raise LevelSnapshotError("invalidation reason is required")
    return replace(
        snapshot,
        lifecycle="invalidated",
        invalidated_at_ms=int(invalidated_at_ms),
        invalidation_reason=str(reason),
    )


def level_snapshot_to_dict(snapshot: LevelSnapshotV1) -> dict[str, Any]:
    return {
        "schema": snapshot.schema,
        "level_id": snapshot.level_id,
        "snapshot_id": snapshot.snapshot_id,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "interval_ms": snapshot.interval_ms,
        "kind": snapshot.kind,
        "lifecycle": snapshot.lifecycle,
        "zone_low": snapshot.zone_low,
        "level": snapshot.level,
        "zone_high": snapshot.zone_high,
        "atr_at_creation": snapshot.atr_at_creation,
        "confirmed_pivots": [item.__dict__ for item in snapshot.confirmed_pivots],
        "respect_history": [item.__dict__ for item in snapshot.respect_history],
        "created_at_ms": snapshot.created_at_ms,
        "valid_at_ms": snapshot.valid_at_ms,
        "source_start_ts_ms": snapshot.source_start_ts_ms,
        "source_end_close_ms": snapshot.source_end_close_ms,
        "source_bars_sha256": snapshot.source_bars_sha256,
        "provider_fingerprint": snapshot.provider_fingerprint,
        "config_sha256": snapshot.config_sha256,
        "payload_sha256": snapshot.payload_sha256,
        "flipped_at_ms": snapshot.flipped_at_ms,
        "invalidated_at_ms": snapshot.invalidated_at_ms,
        "invalidation_reason": snapshot.invalidation_reason,
    }


def level_snapshot_from_dict(raw: object) -> LevelSnapshotV1:
    if not isinstance(raw, Mapping):
        raise LevelSnapshotError("level snapshot payload must be an object")
    keys = {
        "schema", "level_id", "snapshot_id", "symbol", "timeframe", "interval_ms", "kind",
        "lifecycle", "zone_low", "level", "zone_high", "atr_at_creation",
        "confirmed_pivots", "respect_history", "created_at_ms", "valid_at_ms",
        "source_start_ts_ms", "source_end_close_ms", "source_bars_sha256",
        "provider_fingerprint", "config_sha256", "payload_sha256",
        "flipped_at_ms", "invalidated_at_ms", "invalidation_reason",
    }
    if set(raw) != keys:
        raise LevelSnapshotError("level snapshot keys mismatch")
    pivots_raw, respects_raw = raw["confirmed_pivots"], raw["respect_history"]
    if not isinstance(pivots_raw, list) or not isinstance(respects_raw, list):
        raise LevelSnapshotError("level evidence must be arrays")
    try:
        pivots = tuple(ConfirmedPivotV1(**dict(item)) for item in pivots_raw)
        respects = tuple(LevelRespectV1(**dict(item)) for item in respects_raw)
        return LevelSnapshotV1(
            schema=str(raw["schema"]), level_id=str(raw["level_id"]),
            snapshot_id=str(raw["snapshot_id"]),
            symbol=str(raw["symbol"]), timeframe=str(raw["timeframe"]),
            interval_ms=int(raw["interval_ms"]), kind=str(raw["kind"]),
            lifecycle=str(raw["lifecycle"]), zone_low=float(raw["zone_low"]),
            level=float(raw["level"]), zone_high=float(raw["zone_high"]),
            atr_at_creation=float(raw["atr_at_creation"]), confirmed_pivots=pivots,
            respect_history=respects, created_at_ms=int(raw["created_at_ms"]),
            valid_at_ms=int(raw["valid_at_ms"]),
            source_start_ts_ms=int(raw["source_start_ts_ms"]),
            source_end_close_ms=int(raw["source_end_close_ms"]),
            source_bars_sha256=str(raw["source_bars_sha256"]),
            provider_fingerprint=str(raw["provider_fingerprint"]),
            config_sha256=str(raw["config_sha256"]),
            payload_sha256=str(raw["payload_sha256"]),
            flipped_at_ms=None if raw["flipped_at_ms"] is None else int(raw["flipped_at_ms"]),
            invalidated_at_ms=(None if raw["invalidated_at_ms"] is None else int(raw["invalidated_at_ms"])),
            invalidation_reason=str(raw["invalidation_reason"]),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise LevelSnapshotError(f"invalid level snapshot payload: {exc}") from exc


__all__ = [
    "ConfirmedPivotV1", "LEVEL_SNAPSHOT_SCHEMA", "LevelRespectV1",
    "LevelSnapshotConfigV1", "LevelSnapshotError", "LevelSnapshotV1",
    "build_resistance_snapshot_v1", "flip_level_snapshot_v1",
    "invalidate_level_snapshot_v1", "level_snapshot_from_dict",
    "level_snapshot_to_dict", "source_bars_sha256",
]
