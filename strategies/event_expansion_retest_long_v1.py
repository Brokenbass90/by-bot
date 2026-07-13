"""Research-only expansion -> hold -> first-retest continuation (long-only).

The sleeve consumes a frozen :class:`LevelSnapshotV1`; it never redraws a
level from signal bars.  Its pure state machine advances on closed M5/M15 bars
and can emit one plan for the *next* bar open.  There is intentionally no
``TradeSignal`` adapter, runner, broker route, sizing, or live registration.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Optional, Sequence, Tuple

from bot.level_snapshot_v1 import (
    LevelSnapshotError,
    LevelSnapshotV1,
    flip_level_snapshot_v1,
    invalidate_level_snapshot_v1,
)
from bot.market_context import atr


TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5
STRATEGY_NAME = "event_expansion_retest_long_v1"
SIDE_IDENTITY = "long_only"


def _f(row: Sequence[Any], index: int) -> float:
    try:
        return float(row[index])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _ts(row: Sequence[Any]) -> int:
    try:
        return int(float(row[TS]))
    except (IndexError, TypeError, ValueError):
        return -1


def _positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def closed_rows_before(
    rows: Sequence[Sequence[Any]], *, as_of_ms: int, interval_ms: int
) -> list[list[float]]:
    """Return valid unique bars closed by ``as_of_ms``; ignore an open tail."""
    if interval_ms <= 0:
        raise ValueError("interval_ms must be positive")
    out: list[list[float]] = []
    seen: set[int] = set()
    previous = -1
    for raw in rows:
        ts = _ts(raw)
        if ts < 0:
            raise ValueError("invalid signal timestamp")
        if ts + int(interval_ms) > int(as_of_ms):
            continue
        if ts % int(interval_ms) != 0:
            raise ValueError("signal timestamp is off its interval grid")
        if ts in seen or ts <= previous:
            raise ValueError("closed signal rows are duplicate or unordered")
        if previous >= 0 and ts - previous != int(interval_ms):
            raise ValueError("closed signal rows contain a gap")
        values = [_f(raw, index) for index in range(6)]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("closed signal row contains non-finite values")
        _, o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c, h):
            raise ValueError("closed signal row has invalid OHLCV geometry")
        out.append([float(ts), o, h, l, c, v])
        seen.add(ts)
        previous = ts
    return out


@dataclass(frozen=True)
class ExpansionRetestLongConfig:
    signal_interval_min: int = 5
    atr_period: int = 14
    min_history_bars: int = 40
    min_event_range_atr: float = 1.25
    min_event_body_fraction: float = 0.45
    min_event_return_pct: float = 0.01
    volume_baseline_bars: int = 24
    min_volume_multiple: float = 1.25
    breakout_buffer_atr: float = 0.08
    preclose_tolerance_atr: float = 0.20
    max_gap_atr: float = 0.75
    min_respects: int = 2
    hold_bars: int = 2
    hold_buffer_atr: float = 0.03
    retest_touch_atr: float = 0.10
    max_retest_pierce_atr: float = 0.20
    higher_low_right_bars: int = 2
    structure_break_buffer_atr: float = 0.05
    max_retest_confirmation_bars: int = 12
    event_expiry_bars: int = 48
    memory_limit: int = 512

    def __post_init__(self) -> None:
        for name in (
            "signal_interval_min", "atr_period", "min_history_bars",
            "volume_baseline_bars", "min_respects", "hold_bars",
            "higher_low_right_bars", "max_retest_confirmation_bars",
            "event_expiry_bars", "memory_limit",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.min_history_bars < max(self.atr_period + 3, self.volume_baseline_bars + 2):
            raise ValueError("min_history_bars is too short for causal indicators")
        if self.min_respects < 2:
            raise ValueError("min_respects must preserve the two-respect level contract")
        if self.max_retest_confirmation_bars <= self.higher_low_right_bars:
            raise ValueError("retest confirmation window cannot precede higher-low confirmation")
        if self.event_expiry_bars <= self.hold_bars + self.higher_low_right_bars + 1:
            raise ValueError("event expiry is too short for the required causal stages")
        for name in (
            "min_event_range_atr", "min_event_body_fraction", "min_event_return_pct",
            "min_volume_multiple", "breakout_buffer_atr", "preclose_tolerance_atr",
            "max_gap_atr", "hold_buffer_atr", "retest_touch_atr",
            "max_retest_pierce_atr", "structure_break_buffer_atr",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not 0 < self.min_event_body_fraction <= 1:
            raise ValueError("min_event_body_fraction must be in (0, 1]")
        if min(
            self.min_event_range_atr, self.min_event_return_pct, self.min_volume_multiple
        ) <= 0:
            raise ValueError("event expansion thresholds must be positive")

    @property
    def interval_ms(self) -> int:
        return max(1, int(self.signal_interval_min)) * 60_000


class LongEventStage(str, Enum):
    EXPANDED = "expanded"
    HELD_ABOVE = "held_above"
    FIRST_RETEST = "first_retest"
    HIGHER_LOW_CONFIRMED = "higher_low_confirmed"
    PLAN_EMITTED = "plan_emitted"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


TERMINAL_STAGES = frozenset(
    {LongEventStage.PLAN_EMITTED, LongEventStage.INVALIDATED, LongEventStage.EXPIRED}
)


@dataclass(frozen=True)
class LongExpansionEvent:
    event_id: str
    strategy: str
    symbol: str
    side: str
    expansion_ts: int
    expansion_open: float
    expansion_high: float
    expansion_low: float
    expansion_close: float
    expansion_volume: float
    initial_atr: float
    signal_interval_ms: int
    config_sha256: str
    level_snapshot: LevelSnapshotV1
    expires_ts: int

    def __post_init__(self) -> None:
        if self.strategy != STRATEGY_NAME or self.side != "long":
            raise ValueError("expansion-retest events are physically long-only")
        if not self.event_id or self.symbol != self.symbol.upper():
            raise ValueError("event identity/symbol is invalid")
        if self.level_snapshot.symbol != self.symbol or self.level_snapshot.lifecycle != "flip_support":
            raise ValueError("event needs the matching flipped level snapshot")
        if self.level_snapshot.flipped_at_ms != self.expansion_ts:
            raise ValueError("level flip and expansion timestamps must match")
        if (
            self.signal_interval_ms <= 0
            or self.expansion_ts % self.signal_interval_ms != 0
            or self.expires_ts <= self.expansion_ts
            or (self.expires_ts - self.expansion_ts) % self.signal_interval_ms != 0
        ):
            raise ValueError("event signal timeline is off-grid")
        if len(self.config_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.config_sha256):
            raise ValueError("event config_sha256 is invalid")
        if self.event_id != make_event_id(
            self.symbol, self.expansion_ts, self.level_snapshot.snapshot_id,
            self.config_sha256,
        ):
            raise ValueError("event_id does not bind snapshot/config identity")
        if not all(
            _positive(value)
            for value in (
                self.expansion_open, self.expansion_high, self.expansion_low,
                self.expansion_close, self.expansion_volume, self.initial_atr,
            )
        ):
            raise ValueError("event OHLCV/ATR must be positive")


@dataclass(frozen=True)
class LongEventState:
    event: LongExpansionEvent
    stage: LongEventStage
    last_processed_ts: int
    hold_count: int = 0
    first_retest_ts: Optional[int] = None
    retest_low: Optional[float] = None
    structure_level: Optional[float] = None
    terminal_reason: str = ""


@dataclass(frozen=True)
class LongNextOpenPlan:
    event_id: str
    level_id: str
    strategy: str
    symbol: str
    side: str
    signal_ts: int
    valid_from_ts: int
    entry_type: str
    entry_reference: float
    executable: bool
    preflight_status: str
    reason: str

    def __post_init__(self) -> None:
        if self.strategy != STRATEGY_NAME or self.side != "long":
            raise ValueError("expansion-retest plans are physically long-only")
        if self.entry_type != "market_next_open" or self.valid_from_ts <= self.signal_ts:
            raise ValueError("plan must target a later next-open decision")
        if not self.event_id or not self.level_id or not _positive(self.entry_reference):
            raise ValueError("plan identity/reference is invalid")
        if self.executable or self.preflight_status != "BLOCKED_RESEARCH_MECHANICS":
            raise ValueError("v1 mechanics plans are explicitly non-executable")


@dataclass(frozen=True)
class LongSleeveState:
    active: Optional[LongEventState] = None
    seen_event_ids: Tuple[str, ...] = ()
    planned_event_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class LongSleeveStep:
    state: LongSleeveState
    plan: Optional[LongNextOpenPlan]
    reason: str


def config_sha256(cfg: ExpansionRetestLongConfig) -> str:
    payload = json.dumps(
        asdict(cfg), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_closed_input(
    rows: Sequence[Sequence[Any]], cfg: ExpansionRetestLongConfig
) -> list[list[float]]:
    if not rows:
        return []
    latest_ts = _ts(rows[-1])
    if latest_ts < 0:
        raise ValueError("invalid latest signal timestamp")
    validated = closed_rows_before(
        rows,
        as_of_ms=latest_ts + cfg.interval_ms,
        interval_ms=cfg.interval_ms,
    )
    if len(validated) != len(rows):
        raise ValueError("signal input is not an exact closed-bar sequence")
    return validated


def make_event_id(
    symbol: str, expansion_ts: int, snapshot_id: str, config_fingerprint: str
) -> str:
    payload = (
        f"{STRATEGY_NAME}|{str(symbol).upper()}|long|{int(expansion_ts)}|"
        f"{snapshot_id}|{config_fingerprint}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _eligible_level(
    snapshot: LevelSnapshotV1,
    *,
    symbol: str,
    event_ts: int,
    pre_close: float,
    event_open: float,
    event_close: float,
    atr_value: float,
    cfg: ExpansionRetestLongConfig,
) -> bool:
    return bool(
        snapshot.symbol == symbol
        and snapshot.timeframe in {"H1", "H4"}
        and snapshot.lifecycle == "resistance"
        and snapshot.created_at_ms <= event_ts
        and snapshot.valid_at_ms <= event_ts
        and snapshot.source_end_close_ms <= event_ts
        and len(snapshot.respect_history) >= cfg.min_respects
        and pre_close <= snapshot.zone_high + cfg.preclose_tolerance_atr * atr_value
        and event_close > snapshot.zone_high + cfg.breakout_buffer_atr * atr_value
        and event_open <= snapshot.zone_high + cfg.max_gap_atr * atr_value
    )


def detect_expansion_event(
    symbol: str,
    closed_rows: Sequence[Sequence[Any]],
    level_snapshots: Sequence[LevelSnapshotV1],
    cfg: ExpansionRetestLongConfig,
) -> Optional[LongEventState]:
    need = max(cfg.min_history_bars, cfg.atr_period + 3, cfg.volume_baseline_bars + 2)
    if len(closed_rows) < need:
        return None
    canonical_symbol = str(symbol or "").upper()
    if not canonical_symbol or canonical_symbol != str(symbol or ""):
        raise ValueError("symbol must already be canonical uppercase")
    rows = _validate_closed_input(closed_rows, cfg)
    pre, bar = rows[:-1], rows[-1]
    a = atr(pre, cfg.atr_period)
    if not _positive(a):
        return None
    o, h, l, c, v = (_f(bar, index) for index in (OPEN, HIGH, LOW, CLOSE, VOL))
    bar_range = h - l
    baseline = [_f(row, VOL) for row in pre[-cfg.volume_baseline_bars :]]
    baseline_volume = sum(baseline) / len(baseline) if baseline else 0.0
    prior_close = _f(pre[-1], CLOSE)
    if not (
        c > o
        and bar_range / a >= cfg.min_event_range_atr
        and (c - o) / max(1e-12, bar_range) >= cfg.min_event_body_fraction
        and (c - prior_close) / max(1e-12, prior_close) >= cfg.min_event_return_pct
        and baseline_volume > 0
        and v / baseline_volume >= cfg.min_volume_multiple
    ):
        return None
    event_ts = _ts(bar)
    eligible = [
        snapshot
        for snapshot in level_snapshots
        if _eligible_level(
            snapshot, symbol=canonical_symbol, event_ts=event_ts,
            pre_close=prior_close, event_open=o, event_close=c,
            atr_value=a, cfg=cfg,
        )
    ]
    if not eligible:
        return None
    # H4 wins a tie; otherwise use the closest frozen breakout zone.
    frozen = min(
        eligible,
        key=lambda item: (abs(item.zone_high - prior_close), 0 if item.timeframe == "H4" else 1),
    )
    try:
        flipped = flip_level_snapshot_v1(
            frozen, breakout_ts_ms=event_ts, breakout_close=c
        )
    except LevelSnapshotError:
        return None
    cfg_sha = config_sha256(cfg)
    event = LongExpansionEvent(
        event_id=make_event_id(canonical_symbol, event_ts, frozen.snapshot_id, cfg_sha),
        strategy=STRATEGY_NAME,
        symbol=canonical_symbol,
        side="long",
        expansion_ts=event_ts,
        expansion_open=o,
        expansion_high=h,
        expansion_low=l,
        expansion_close=c,
        expansion_volume=v,
        initial_atr=a,
        signal_interval_ms=cfg.interval_ms,
        config_sha256=cfg_sha,
        level_snapshot=flipped,
        expires_ts=event_ts + cfg.event_expiry_bars * cfg.interval_ms,
    )
    return LongEventState(event, LongEventStage.EXPANDED, event_ts)


def _invalidate(
    state: LongEventState, *, ts: int, close: float, reason: str
) -> LongEventState:
    snapshot = state.event.level_snapshot
    try:
        invalidated = invalidate_level_snapshot_v1(
            snapshot, invalidated_at_ms=ts, close=close, reason=reason
        )
    except LevelSnapshotError:
        # Event mechanics can fail without a close through the level (for
        # example retest-before-hold).  Preserve the still-valid level honestly.
        invalidated = snapshot
    return replace(
        state,
        event=replace(state.event, level_snapshot=invalidated),
        stage=LongEventStage.INVALIDATED,
        last_processed_ts=ts,
        terminal_reason=reason,
    )


def advance_event(
    state: LongEventState,
    closed_rows: Sequence[Sequence[Any]],
    cfg: ExpansionRetestLongConfig,
) -> tuple[LongEventState, Optional[LongNextOpenPlan], str]:
    if not closed_rows:
        return state, None, "no_rows"
    rows = _validate_closed_input(closed_rows, cfg)
    bar, ts = rows[-1], _ts(rows[-1])
    if ts <= state.last_processed_ts:
        return state, None, "duplicate_or_old_bar"
    if state.stage in TERMINAL_STAGES:
        return state, None, f"terminal:{state.stage.value}"
    if ts > state.event.expires_ts:
        return replace(
            state, stage=LongEventStage.EXPIRED, last_processed_ts=ts,
            terminal_reason="event_expiry",
        ), None, "event_expired"
    a = atr(rows, cfg.atr_period, exclude_last=True)
    if not _positive(a):
        return _invalidate(state, ts=ts, close=_f(bar, CLOSE), reason="atr_invalid"), None, "atr_invalid"
    snapshot = state.event.level_snapshot
    o, h, l, c = (_f(bar, index) for index in (OPEN, HIGH, LOW, CLOSE))
    if c < snapshot.zone_low:
        return _invalidate(state, ts=ts, close=c, reason="flip_close_failed"), None, "flip_close_failed"

    if state.stage == LongEventStage.EXPANDED:
        touched = l <= snapshot.zone_high + cfg.retest_touch_atr * a
        if touched:
            return _invalidate(state, ts=ts, close=c, reason="retest_before_hold"), None, "retest_before_hold"
        held = c >= snapshot.zone_high + cfg.hold_buffer_atr * a
        count = state.hold_count + 1 if held else 0
        if count >= cfg.hold_bars:
            return replace(
                state, stage=LongEventStage.HELD_ABOVE,
                last_processed_ts=ts, hold_count=count,
            ), None, "hold_confirmed"
        return replace(state, last_processed_ts=ts, hold_count=count), None, "holding_above" if held else "hold_not_confirmed"

    if state.stage == LongEventStage.HELD_ABOVE:
        touched = l <= snapshot.zone_high + cfg.retest_touch_atr * a
        if not touched:
            return replace(state, last_processed_ts=ts), None, "waiting_first_retest"
        prior_close = _f(rows[-2], CLOSE)
        if prior_close <= snapshot.zone_high:
            return _invalidate(state, ts=ts, close=c, reason="retest_not_from_above"), None, "retest_not_from_above"
        if l < snapshot.zone_low - cfg.max_retest_pierce_atr * a or c < snapshot.level:
            return _invalidate(state, ts=ts, close=c, reason="first_retest_failed"), None, "first_retest_failed"
        between = [
            row for row in rows
            if state.event.expansion_ts < _ts(row) < ts
        ]
        if not between:
            return _invalidate(state, ts=ts, close=c, reason="structure_reference_missing"), None, "structure_reference_missing"
        structure_level = max(_f(row, HIGH) for row in between)
        return replace(
            state, stage=LongEventStage.FIRST_RETEST, last_processed_ts=ts,
            first_retest_ts=ts, retest_low=l, structure_level=structure_level,
        ), None, "first_retest_confirmed"

    if state.stage == LongEventStage.FIRST_RETEST:
        assert state.first_retest_ts is not None and state.structure_level is not None
        age = (ts - state.first_retest_ts) // cfg.interval_ms
        if age > cfg.max_retest_confirmation_bars:
            return replace(
                state, stage=LongEventStage.EXPIRED, last_processed_ts=ts,
                terminal_reason="structure_confirmation_expiry",
            ), None, "structure_confirmation_expired"
        retest_index = next(
            (index for index, row in enumerate(rows) if _ts(row) == state.first_retest_ts),
            -1,
        )
        if retest_index < 0:
            return _invalidate(state, ts=ts, close=c, reason="retest_bar_missing"), None, "retest_bar_missing"
        confirming = rows[retest_index + 1 :]
        if any(_f(item, LOW) <= float(state.retest_low or 0.0) for item in confirming):
            return _invalidate(state, ts=ts, close=c, reason="higher_low_failed"), None, "higher_low_failed"
        if len(confirming) < cfg.higher_low_right_bars:
            return replace(state, last_processed_ts=ts), None, "waiting_higher_low_confirmation"
        return replace(
            state, stage=LongEventStage.HIGHER_LOW_CONFIRMED,
            last_processed_ts=ts,
        ), None, "higher_low_confirmed"

    if state.stage == LongEventStage.HIGHER_LOW_CONFIRMED:
        assert state.first_retest_ts is not None and state.structure_level is not None
        age = (ts - state.first_retest_ts) // cfg.interval_ms
        if age > cfg.max_retest_confirmation_bars:
            return replace(
                state, stage=LongEventStage.EXPIRED, last_processed_ts=ts,
                terminal_reason="structure_confirmation_expiry",
            ), None, "structure_confirmation_expired"
        threshold = state.structure_level + cfg.structure_break_buffer_atr * a
        prior_close = _f(rows[-2], CLOSE)
        confirmed = bool(ts > state.first_retest_ts and prior_close <= threshold and c > threshold and c > o)
        if not confirmed:
            return replace(state, last_processed_ts=ts), None, "waiting_bullish_structure_break"
        plan = LongNextOpenPlan(
            event_id=state.event.event_id,
            level_id=snapshot.level_id,
            strategy=STRATEGY_NAME,
            symbol=state.event.symbol,
            side="long",
            signal_ts=ts,
            valid_from_ts=ts + cfg.interval_ms,
            entry_type="market_next_open",
            entry_reference=c,
            executable=False,
            preflight_status="BLOCKED_RESEARCH_MECHANICS",
            reason=(
                f"event={state.event.event_id} level={snapshot.level_id} "
                "breakout_hold_first_retest_bullish_structure"
            ),
        )
        return replace(
            state, stage=LongEventStage.PLAN_EMITTED,
            last_processed_ts=ts, terminal_reason="one_plan_emitted",
        ), plan, "plan_ready"
    return replace(state, last_processed_ts=ts), None, "unhandled_stage"


def _remember(values: Tuple[str, ...], value: str, limit: int) -> Tuple[str, ...]:
    if value in values:
        return values
    return tuple((values + (value,))[-max(1, int(limit)) :])


def sleeve_step(
    symbol: str,
    closed_rows: Sequence[Sequence[Any]],
    level_snapshots: Sequence[LevelSnapshotV1],
    prior: LongSleeveState,
    cfg: ExpansionRetestLongConfig,
) -> LongSleeveStep:
    if not closed_rows:
        return LongSleeveStep(prior, None, "no_rows")
    active = prior.active
    if active is not None and active.stage in TERMINAL_STAGES:
        if _ts(closed_rows[-1]) <= active.last_processed_ts:
            return LongSleeveStep(prior, None, f"terminal:{active.stage.value}")
        active = None
    if active is None:
        detected = detect_expansion_event(symbol, closed_rows, level_snapshots, cfg)
        if detected is None:
            return LongSleeveStep(replace(prior, active=None), None, "no_expansion_event")
        event_id = detected.event.event_id
        if event_id in prior.seen_event_ids:
            return LongSleeveStep(replace(prior, active=None), None, "event_already_seen")
        return LongSleeveStep(
            LongSleeveState(
                active=detected,
                seen_event_ids=_remember(prior.seen_event_ids, event_id, cfg.memory_limit),
                planned_event_ids=prior.planned_event_ids,
            ), None, "event_created",
        )
    advanced, plan, reason = advance_event(active, closed_rows, cfg)
    planned = prior.planned_event_ids
    if plan is not None:
        if plan.event_id in planned:
            plan, reason = None, "plan_already_emitted"
        else:
            planned = _remember(planned, plan.event_id, cfg.memory_limit)
    return LongSleeveStep(
        LongSleeveState(advanced, prior.seen_event_ids, planned), plan, reason
    )


class EventExpansionRetestLongV1Research:
    """Pure mechanics scaffold; performance is blocked until a prereg runner."""

    RESEARCH_ONLY = True
    LIVE_READY = False
    SIDE_IDENTITY = SIDE_IDENTITY
    REQUIRES_PERSISTED_EVENT_STATE = True

    def __init__(self, cfg: Optional[ExpansionRetestLongConfig] = None):
        self.cfg = cfg or ExpansionRetestLongConfig()
        self._states: dict[str, LongSleeveState] = {}

    def process_closed_rows(
        self, symbol: str, rows: Sequence[Sequence[Any]],
        level_snapshots: Sequence[LevelSnapshotV1],
    ) -> LongSleeveStep:
        canonical = str(symbol).upper()
        step = sleeve_step(
            canonical, rows, level_snapshots,
            self._states.get(canonical, LongSleeveState()), self.cfg,
        )
        self._states[canonical] = step.state
        return step


__all__ = [
    "EventExpansionRetestLongV1Research", "ExpansionRetestLongConfig",
    "LongEventStage", "LongEventState", "LongExpansionEvent",
    "LongNextOpenPlan", "LongSleeveState", "LongSleeveStep", "SIDE_IDENTITY",
    "STRATEGY_NAME", "advance_event", "closed_rows_before",
    "config_sha256", "detect_expansion_event", "make_event_id", "sleeve_step",
]
