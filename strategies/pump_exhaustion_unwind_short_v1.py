"""Research-only event-first pump exhaustion unwind (strictly short-only).

This module deliberately has no live wiring.  It replaces the legacy InPlay
"signal on every bar while a 4H breakout is still visible" contract with an
explicit, immutable event and a small state machine:

    expansion -> exhaustion -> bearish CHoCH -> failed reclaim -> one plan

All price structure is frozen from bars that closed *before* the expansion.
The state-transition functions are pure: callers pass rows and prior state and
receive a new state.  The optional strategy wrapper only adapts those functions
to the repository's ``TradeSignal`` research contract.

Rows are ascending ``[ts_ms, open, high, low, close, volume]``.  Timestamps are
bar-open timestamps.  ``closed_rows_before`` is the single closed-bar boundary.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Optional, Sequence, Tuple

from bot.inplay_volume_universe import InplayVolumeScore, score_inplay_volume
from bot.market_context import atr, horizontal_levels, sloped_level
from bot.pump_exhaustion import ImpulseFadeState, impulse_exhaustion
from bot.retest_quality import RetestScore, score_retest
from bot.structure_break import StructureBreak, structure_break
from strategies.signals import TradeSignal


TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5
STRATEGY_NAME = "pump_exhaustion_unwind_short_v1"


def _f(row: Sequence[Any], idx: int) -> float:
    try:
        return float(row[idx])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _finite_positive(value: float) -> bool:
    return math.isfinite(float(value)) and float(value) > 0.0


def _row_ts(row: Sequence[Any]) -> int:
    try:
        return int(float(row[TS]))
    except (IndexError, TypeError, ValueError):
        return -1


def closed_rows_before(
    rows: Sequence[Sequence[Any]],
    *,
    as_of_ms: int,
    interval_ms: int,
) -> list[list[float]]:
    """Return unique, valid bars whose close time is no later than ``as_of_ms``.

    The function is intentionally fail-closed: malformed OHLC rows, duplicate
    timestamps, and a still-open latest bar cannot influence a decision.
    """
    if interval_ms <= 0:
        raise ValueError("interval_ms must be positive")
    by_ts: dict[int, list[float]] = {}
    for raw in rows:
        ts = _row_ts(raw)
        if ts < 0 or ts + int(interval_ms) > int(as_of_ms) or ts in by_ts:
            continue
        vals = [_f(raw, i) for i in range(6)]
        if not all(math.isfinite(v) for v in vals):
            continue
        _, o, h, l, c, v = vals
        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c, h):
            continue
        by_ts[ts] = [float(ts), o, h, l, c, v]
    return [by_ts[ts] for ts in sorted(by_ts)]


@dataclass(frozen=True)
class PumpUnwindConfig:
    signal_interval_min: int = 5
    history_limit: int = 720
    atr_period: int = 14

    # Frozen pre-event structure.
    level_lookback: int = 144
    liquidity_lookback: int = 48
    pivot_left: int = 2
    pivot_right: int = 2
    horizontal_tolerance_atr: float = 0.35
    min_horizontal_touches: int = 2
    sloped_min_pivots: int = 2
    sloped_min_r2: float = 0.45
    max_level_distance_atr: float = 3.0
    breakout_buffer_atr: float = 0.08
    preclose_level_tolerance_atr: float = 0.35

    # Expansion and relative-volume event.
    expansion_lookback_bars: int = 6
    min_expansion_pct: float = 0.035
    min_event_body_frac: float = 0.45
    min_event_range_atr: float = 1.20
    volume_recent_bars: int = 3
    volume_baseline_bars: int = 48
    min_recent_quote_usd: float = 250_000.0
    min_inflow_mult: float = 1.8
    min_inflow_z: float = 1.5
    max_abs_recent_return_pct: float = 25.0

    # Event-specific exhaustion, plus the shared exhaustion detector.
    exhaustion_impulse_window: int = 8
    exhaustion_baseline_window: int = 24
    exhaustion_peak_window: int = 8
    exhaustion_min_impulse_pct: float = 0.035
    exhaustion_min_vol_mult: float = 1.8
    exhaustion_peak_fade_ratio: float = 0.75
    exhaustion_min_rejection_frac: float = 0.25
    exhaustion_confirm_retrace: float = 0.25
    min_bars_after_expansion: int = 1
    require_shared_exhaustion: bool = True

    # Bearish structure shift and first failed reclaim.
    choch_left: int = 2
    choch_right: int = 2
    choch_buffer_atr: float = 0.05
    retest_touch_atr: float = 0.25
    retest_close_below_atr: float = 0.03
    retest_min_upper_wick_frac: float = 0.12
    retest_min_quality: float = 0.35
    retest_volume_mult: float = 1.0

    # Plan and lifecycle.  The plan is for the next bar open, never same-close.
    stop_pad_atr: float = 0.15
    min_stop_atr: float = 0.25
    max_stop_atr: float = 8.0
    max_stop_pct: float = 0.12
    tp1_rr: float = 1.0
    tp_rr: float = 2.0
    event_expiry_bars: int = 48
    post_choch_expiry_bars: int = 12
    invalidation_close_atr: float = 0.15
    seen_event_memory: int = 512

    @property
    def interval_ms(self) -> int:
        return max(1, int(self.signal_interval_min)) * 60_000


@dataclass(frozen=True)
class FrozenHighLevels:
    """All values were computed without the expansion bar and never mutate."""

    horizontal_high: Optional[float]
    sloped_high: Optional[float]
    liquidity_high: float
    anchor_level: float
    anchor_source: str
    crossed_sources: Tuple[str, ...]


@dataclass(frozen=True)
class PumpExpansionEvent:
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
    base_price: float
    initial_atr: float
    levels: FrozenHighLevels
    expires_ts: int

    def __post_init__(self) -> None:
        if self.strategy != STRATEGY_NAME or self.side != "short":
            raise ValueError("pump unwind events are strictly short-only")
        if not self.event_id or not self.symbol:
            raise ValueError("event_id and symbol are required")
        if not all(
            _finite_positive(v)
            for v in (
                self.expansion_open,
                self.expansion_high,
                self.expansion_low,
                self.expansion_close,
                self.base_price,
                self.initial_atr,
                self.levels.anchor_level,
            )
        ):
            raise ValueError("event prices and ATR must be positive")


class EventStage(str, Enum):
    EXPANDED = "expanded"
    EXHAUSTED = "exhausted"
    CHOCH_CONFIRMED = "choch_confirmed"
    PLAN_EMITTED = "plan_emitted"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


TERMINAL_STAGES = frozenset(
    {EventStage.PLAN_EMITTED, EventStage.INVALIDATED, EventStage.EXPIRED}
)


@dataclass(frozen=True)
class PumpEventState:
    event: PumpExpansionEvent
    stage: EventStage
    last_processed_ts: int
    peak_price: float
    exhaustion_ts: Optional[int] = None
    choch_ts: Optional[int] = None
    choch_level: Optional[float] = None
    terminal_reason: str = ""


@dataclass(frozen=True)
class PumpUnwindShortPlan:
    event_id: str
    strategy: str
    symbol: str
    side: str
    signal_ts: int
    valid_from_ts: int
    entry_type: str
    entry_reference: float
    stop: float
    target_1: float
    target_2: float
    risk: float
    choch_level: float
    event_peak: float
    reason: str

    def __post_init__(self) -> None:
        if self.strategy != STRATEGY_NAME or self.side != "short":
            raise ValueError("pump unwind plans are strictly short-only")
        if self.entry_type != "market_next_open":
            raise ValueError("research plan must use market_next_open")
        if not (0 < self.target_2 < self.target_1 < self.entry_reference < self.stop):
            raise ValueError("invalid short plan geometry")
        if not _finite_positive(self.risk):
            raise ValueError("risk must be positive")


@dataclass(frozen=True)
class SleeveState:
    active: Optional[PumpEventState] = None
    seen_event_ids: Tuple[str, ...] = ()
    planned_event_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SleeveStep:
    state: SleeveState
    plan: Optional[PumpUnwindShortPlan]
    reason: str


@dataclass(frozen=True)
class ExhaustionEvidence:
    passed: bool
    peak_price: float
    retrace_frac: float
    volume_fade_ratio: float
    upper_wick_frac: float
    shared: ImpulseFadeState
    reason: str


@dataclass(frozen=True)
class RetestEvidence:
    passed: bool
    quality: RetestScore
    touch: bool
    closed_below: bool
    rejected: bool
    reason: str


def _stable_price(value: Optional[float]) -> str:
    return "none" if value is None else format(float(value), ".12g")


def make_event_id(
    symbol: str,
    expansion_ts: int,
    levels: FrozenHighLevels,
) -> str:
    """Deterministic identity; the returned value is stored on a frozen event."""
    payload = "|".join(
        (
            STRATEGY_NAME,
            str(symbol).upper(),
            "short",
            str(int(expansion_ts)),
            _stable_price(levels.horizontal_high),
            _stable_price(levels.sloped_high),
            _stable_price(levels.liquidity_high),
            _stable_price(levels.anchor_level),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def freeze_pre_event_highs(
    pre_event_rows: Sequence[Sequence[Any]],
    expansion_row: Sequence[Any],
    cfg: PumpUnwindConfig,
) -> Optional[FrozenHighLevels]:
    """Freeze crossed horizontal, sloped, and rolling-liquidity highs."""
    rows = [list(r) for r in pre_event_rows[-max(30, int(cfg.level_lookback)) :]]
    if len(rows) < max(30, cfg.atr_period + cfg.pivot_left + cfg.pivot_right + 3):
        return None
    a = atr(rows, cfg.atr_period)
    if not _finite_positive(a):
        return None
    pre_close = _f(rows[-1], CLOSE)
    event_close = _f(expansion_row, CLOSE)
    if not (_finite_positive(pre_close) and _finite_positive(event_close)):
        return None

    max_dist = float(cfg.max_level_distance_atr) * a
    pre_tol = float(cfg.preclose_level_tolerance_atr) * a
    break_buf = float(cfg.breakout_buffer_atr) * a

    def crossed(level: float) -> bool:
        return bool(
            _finite_positive(level)
            and abs(level - pre_close) <= max_dist
            and pre_close <= level + pre_tol
            and event_close >= level + break_buf
        )

    horizontal: Optional[float] = None
    hlevels = horizontal_levels(
        rows,
        side="resistance",
        atr_value=a,
        left=cfg.pivot_left,
        right=cfg.pivot_right,
        tol_atr=cfg.horizontal_tolerance_atr,
        min_touches=cfg.min_horizontal_touches,
    )
    hcands = [float(level["level"]) for level in hlevels if crossed(float(level["level"]))]
    if hcands:
        horizontal = min(hcands, key=lambda value: abs(value - pre_close))

    sloped: Optional[float] = None
    sl = sloped_level(
        rows,
        side="resistance",
        left=cfg.pivot_left,
        right=cfg.pivot_right,
        min_pivots=cfg.sloped_min_pivots,
        min_r2=cfg.sloped_min_r2,
        require_unbroken=True,
        atr_value=a,
    )
    if sl is not None:
        projected = float(sl["level_now"]) + float(sl["slope"])
        if crossed(projected):
            sloped = projected

    liq_rows = rows[-max(3, int(cfg.liquidity_lookback)) :]
    liquidity = max(_f(row, HIGH) for row in liq_rows)

    crossed_map: dict[str, float] = {}
    if horizontal is not None:
        crossed_map["horizontal"] = horizontal
    if sloped is not None:
        crossed_map["sloped"] = sloped
    if crossed(liquidity):
        crossed_map["liquidity"] = liquidity
    if not crossed_map:
        return None

    anchor_source, anchor = max(crossed_map.items(), key=lambda item: item[1])
    return FrozenHighLevels(
        horizontal_high=horizontal,
        sloped_high=sloped,
        liquidity_high=float(liquidity),
        anchor_level=float(anchor),
        anchor_source=str(anchor_source),
        crossed_sources=tuple(sorted(crossed_map)),
    )


def detect_expansion_event(
    symbol: str,
    closed_rows: Sequence[Sequence[Any]],
    cfg: PumpUnwindConfig,
) -> Optional[PumpEventState]:
    """Detect one up-expansion using only the latest *closed* bar."""
    need = max(
        cfg.level_lookback + 1,
        cfg.volume_recent_bars + cfg.volume_baseline_bars,
        cfg.expansion_lookback_bars + 2,
        cfg.atr_period + 3,
    )
    if len(closed_rows) < need:
        return None
    rows = [list(row) for row in closed_rows]
    pre = rows[:-1]
    event_bar = rows[-1]
    a = atr(pre, cfg.atr_period)
    if not _finite_positive(a):
        return None

    o, h, l, c, v = (_f(event_bar, idx) for idx in (OPEN, HIGH, LOW, CLOSE, VOL))
    bar_range = h - l
    body_frac = abs(c - o) / max(1e-12, bar_range)
    range_atr = bar_range / a
    base_price = _f(rows[-cfg.expansion_lookback_bars - 1], CLOSE)
    expansion_pct = (c - base_price) / max(1e-12, base_price)
    if not (
        c > o
        and expansion_pct >= cfg.min_expansion_pct
        and body_frac >= cfg.min_event_body_frac
        and range_atr >= cfg.min_event_range_atr
    ):
        return None

    volume_score: InplayVolumeScore = score_inplay_volume(
        rows,
        recent_bars=cfg.volume_recent_bars,
        baseline_bars=cfg.volume_baseline_bars,
        min_recent_quote_usd=cfg.min_recent_quote_usd,
        min_inflow_mult=cfg.min_inflow_mult,
        min_inflow_z=cfg.min_inflow_z,
        max_abs_recent_return_pct=cfg.max_abs_recent_return_pct,
    )
    if not volume_score.ok:
        return None

    levels = freeze_pre_event_highs(pre, event_bar, cfg)
    if levels is None:
        return None

    event_ts = _row_ts(event_bar)
    event = PumpExpansionEvent(
        event_id=make_event_id(symbol, event_ts, levels),
        strategy=STRATEGY_NAME,
        symbol=str(symbol).upper(),
        side="short",
        expansion_ts=event_ts,
        expansion_open=o,
        expansion_high=h,
        expansion_low=l,
        expansion_close=c,
        expansion_volume=v,
        base_price=base_price,
        initial_atr=a,
        levels=levels,
        expires_ts=event_ts + int(cfg.event_expiry_bars) * cfg.interval_ms,
    )
    return PumpEventState(
        event=event,
        stage=EventStage.EXPANDED,
        last_processed_ts=event_ts,
        peak_price=h,
    )


def exhaustion_evidence(
    state: PumpEventState,
    closed_rows: Sequence[Sequence[Any]],
    cfg: PumpUnwindConfig,
) -> ExhaustionEvidence:
    """Combine event-specific exhaustion with the shared pump detector."""
    rows = [list(row) for row in closed_rows]
    bar = rows[-1]
    peak = max(float(state.peak_price), _f(bar, HIGH))
    impulse_range = max(1e-12, peak - state.event.base_price)
    close = _f(bar, CLOSE)
    retrace = (peak - close) / impulse_range
    volume_fade = _f(bar, VOL) / max(1e-12, state.event.expansion_volume)
    bar_range = max(1e-12, _f(bar, HIGH) - _f(bar, LOW))
    upper_wick = (_f(bar, HIGH) - max(_f(bar, OPEN), close)) / bar_range

    shared = impulse_exhaustion(
        rows,
        impulse_window=cfg.exhaustion_impulse_window,
        baseline_window=cfg.exhaustion_baseline_window,
        peak_window=cfg.exhaustion_peak_window,
        min_impulse_pct=cfg.exhaustion_min_impulse_pct,
        min_vol_mult=cfg.exhaustion_min_vol_mult,
        peak_fade_ratio=cfg.exhaustion_peak_fade_ratio,
        min_rejection_frac=cfg.exhaustion_min_rejection_frac,
        confirm_retrace=cfg.exhaustion_confirm_retrace,
        min_bars=max(
            cfg.exhaustion_baseline_window + cfg.exhaustion_impulse_window + 1,
            cfg.atr_period + 3,
        ),
    )
    age_bars = max(0, (_row_ts(bar) - state.event.expansion_ts) // cfg.interval_ms)
    direct = bool(
        age_bars >= cfg.min_bars_after_expansion
        and retrace >= cfg.exhaustion_confirm_retrace
        and (
            volume_fade <= cfg.exhaustion_peak_fade_ratio
            or upper_wick >= cfg.exhaustion_min_rejection_frac
        )
    )
    passed = bool(direct and (shared.short_ok if cfg.require_shared_exhaustion else True))
    if not direct:
        reason = "event_not_exhausted"
    elif cfg.require_shared_exhaustion and not shared.short_ok:
        reason = f"shared_exhaustion:{shared.reason}"
    else:
        reason = "exhaustion_confirmed"
    return ExhaustionEvidence(
        passed=passed,
        peak_price=peak,
        retrace_frac=retrace,
        volume_fade_ratio=volume_fade,
        upper_wick_frac=upper_wick,
        shared=shared,
        reason=reason,
    )


def bearish_choch(
    closed_rows: Sequence[Sequence[Any]],
    *,
    after_ts: int,
    cfg: PumpUnwindConfig,
) -> StructureBreak:
    """Return only a bearish CHoCH occurring strictly after exhaustion."""
    rows = [list(row) for row in closed_rows]
    if not rows or _row_ts(rows[-1]) <= int(after_ts):
        return StructureBreak(
            False, "none", "none", "range", float("nan"), "none", False, False,
            "before_or_same_as_exhaustion",
        )
    result = structure_break(
        rows,
        left=cfg.choch_left,
        right=cfg.choch_right,
        buffer_atr=cfg.choch_buffer_atr,
    )
    if result.event == "choch" and result.short_ok and result.direction == "down":
        return result
    return replace(
        result,
        event="none",
        direction="none",
        side="none",
        long_ok=False,
        short_ok=False,
        reason=f"not_bearish_choch:{result.reason}",
    )


def failed_reclaim_evidence(
    state: PumpEventState,
    closed_rows: Sequence[Sequence[Any]],
    cfg: PumpUnwindConfig,
) -> RetestEvidence:
    """Confirm the first post-CHoCH retest from below; never retroactive."""
    rows = [list(row) for row in closed_rows]
    if state.choch_ts is None or state.choch_level is None or _row_ts(rows[-1]) <= state.choch_ts:
        blank = RetestScore(
            ok=False,
            entry_ok=False,
            side="none",
            long_ok=False,
            short_ok=False,
            level=float("nan"),
            dist_atr=float("nan"),
            freshness_bars=-1,
            touches=0,
            quality=0.0,
            freshness_score=0.0,
            proximity_score=0.0,
            strength_score=0.0,
            rejection_score=0.0,
            volume_score=0.0,
            reason="before_or_same_as_choch",
        )
        return RetestEvidence(False, blank, False, False, False, blank.reason)

    a = atr(rows, cfg.atr_period, exclude_last=True)
    level = float(state.choch_level)
    bar = rows[-1]
    if not _finite_positive(a):
        quality = score_retest(rows, level, "resistance", min_quality=1.1)
        return RetestEvidence(False, quality, False, False, False, "atr_invalid")
    o, h, l, c = (_f(bar, idx) for idx in (OPEN, HIGH, LOW, CLOSE))
    touch = h >= level - cfg.retest_touch_atr * a
    closed_below = c <= level - cfg.retest_close_below_atr * a
    upper_wick = (h - max(o, c)) / max(1e-12, h - l)
    rejected = bool(c < o or upper_wick >= cfg.retest_min_upper_wick_frac)
    choch_idx = next(
        (idx for idx, row in enumerate(rows) if _row_ts(row) == int(state.choch_ts)),
        max(0, len(rows) - 2),
    )
    # ``score_retest`` needs a strength count and a freshness anchor.  A CHoCH
    # bar is a *break*, not a second touch, so do not manufacture ``touches=2``.
    # Count actual pre-break contacts (collapsing adjacent bars), while using the
    # CHoCH index only as the freshness origin of the newly flipped resistance.
    contact_indices: list[int] = []
    contact_tol = cfg.retest_touch_atr * a
    for idx, prior_bar in enumerate(rows[:choch_idx]):
        if _f(prior_bar, LOW) - contact_tol <= level <= _f(prior_bar, HIGH) + contact_tol:
            if not contact_indices or idx - contact_indices[-1] > 1:
                contact_indices.append(idx)
    structural_contacts = max(1, len(contact_indices))
    quality = score_retest(
        rows,
        level,
        "resistance",
        atr_value=a,
        last_touch_idx=choch_idx,
        touches=structural_contacts,
        entry_band_atr=max(cfg.retest_touch_atr, cfg.retest_close_below_atr + 0.05),
        max_age_bars=cfg.post_choch_expiry_bars,
        vol_mult=cfg.retest_volume_mult,
        min_quality=cfg.retest_min_quality,
    )
    passed = bool(touch and closed_below and rejected and quality.short_ok)
    if not touch:
        reason = "no_retest_touch"
    elif not closed_below:
        reason = "reclaim_succeeded"
    elif not rejected:
        reason = "no_bearish_rejection"
    elif not quality.short_ok:
        reason = f"retest_quality:{quality.reason}"
    else:
        reason = "failed_reclaim_confirmed"
    return RetestEvidence(passed, quality, touch, closed_below, rejected, reason)


def build_short_plan(
    state: PumpEventState,
    closed_rows: Sequence[Sequence[Any]],
    cfg: PumpUnwindConfig,
) -> tuple[Optional[PumpUnwindShortPlan], str]:
    rows = [list(row) for row in closed_rows]
    bar = rows[-1]
    a = atr(rows, cfg.atr_period, exclude_last=True)
    entry = _f(bar, CLOSE)
    if not _finite_positive(a):
        return None, "plan_atr_invalid"
    stop = max(float(state.peak_price), _f(bar, HIGH)) + cfg.stop_pad_atr * a
    risk = stop - entry
    risk_atr = risk / a
    risk_pct = risk / max(1e-12, entry)
    if risk_atr < cfg.min_stop_atr:
        return None, f"plan_stop_too_tight:{risk_atr:.3f}atr"
    if risk_atr > cfg.max_stop_atr or risk_pct > cfg.max_stop_pct:
        return None, f"plan_stop_too_wide:{risk_atr:.3f}atr:{risk_pct:.3%}"
    tp1 = entry - cfg.tp1_rr * risk
    tp2 = entry - cfg.tp_rr * risk
    if not (0 < tp2 < tp1 < entry):
        return None, "plan_targets_invalid"
    ts = _row_ts(bar)
    plan = PumpUnwindShortPlan(
        event_id=state.event.event_id,
        strategy=STRATEGY_NAME,
        symbol=state.event.symbol,
        side="short",
        signal_ts=ts,
        valid_from_ts=ts + cfg.interval_ms,
        entry_type="market_next_open",
        entry_reference=entry,
        stop=stop,
        target_1=tp1,
        target_2=tp2,
        risk=risk,
        choch_level=float(state.choch_level or 0.0),
        event_peak=float(state.peak_price),
        reason=(
            f"event={state.event.event_id} expansion_exhaustion_choch_failed_reclaim "
            f"anchor={state.event.levels.anchor_source}@{state.event.levels.anchor_level:.8g}"
        ),
    )
    return plan, "plan_ready"


def advance_event(
    state: PumpEventState,
    closed_rows: Sequence[Sequence[Any]],
    cfg: PumpUnwindConfig,
) -> tuple[PumpEventState, Optional[PumpUnwindShortPlan], str]:
    """Advance at most one FSM stage on the latest closed bar."""
    if not closed_rows:
        return state, None, "no_rows"
    rows = [list(row) for row in closed_rows]
    bar = rows[-1]
    ts = _row_ts(bar)
    if ts <= state.last_processed_ts:
        return state, None, "duplicate_or_old_bar"
    if state.stage in TERMINAL_STAGES:
        return state, None, f"terminal:{state.stage.value}"
    if ts > state.event.expires_ts:
        return (
            replace(
                state,
                stage=EventStage.EXPIRED,
                last_processed_ts=ts,
                terminal_reason="event_expiry",
            ),
            None,
            "event_expired",
        )

    a = atr(rows, cfg.atr_period, exclude_last=True)
    if not _finite_positive(a):
        return replace(state, last_processed_ts=ts), None, "atr_invalid"
    close = _f(bar, CLOSE)

    if state.stage == EventStage.EXPANDED:
        evidence = exhaustion_evidence(state, rows, cfg)
        if evidence.passed:
            return (
                replace(
                    state,
                    stage=EventStage.EXHAUSTED,
                    last_processed_ts=ts,
                    peak_price=evidence.peak_price,
                    exhaustion_ts=ts,
                ),
                None,
                evidence.reason,
            )
        return (
            replace(
                state,
                last_processed_ts=ts,
                peak_price=max(state.peak_price, _f(bar, HIGH)),
            ),
            None,
            evidence.reason,
        )

    if close > state.peak_price + cfg.invalidation_close_atr * a:
        return (
            replace(
                state,
                stage=EventStage.INVALIDATED,
                last_processed_ts=ts,
                terminal_reason="closed_above_exhaustion_peak",
            ),
            None,
            "event_invalidated_new_high",
        )

    if state.stage == EventStage.EXHAUSTED:
        choch = bearish_choch(rows, after_ts=int(state.exhaustion_ts or 0), cfg=cfg)
        if choch.event == "choch" and choch.short_ok and _finite_positive(choch.level):
            return (
                replace(
                    state,
                    stage=EventStage.CHOCH_CONFIRMED,
                    last_processed_ts=ts,
                    choch_ts=ts,
                    choch_level=float(choch.level),
                ),
                None,
                "bearish_choch_confirmed",
            )
        return replace(state, last_processed_ts=ts), None, choch.reason

    if state.stage == EventStage.CHOCH_CONFIRMED:
        assert state.choch_ts is not None and state.choch_level is not None
        choch_age = (ts - state.choch_ts) // cfg.interval_ms
        if choch_age > cfg.post_choch_expiry_bars:
            return (
                replace(
                    state,
                    stage=EventStage.EXPIRED,
                    last_processed_ts=ts,
                    terminal_reason="post_choch_retest_expiry",
                ),
                None,
                "post_choch_expired",
            )
        if close > state.choch_level + cfg.invalidation_close_atr * a:
            return (
                replace(
                    state,
                    stage=EventStage.INVALIDATED,
                    last_processed_ts=ts,
                    terminal_reason="reclaimed_above_choch_level",
                ),
                None,
                "choch_reclaim_invalidated",
            )
        retest = failed_reclaim_evidence(state, rows, cfg)
        if not retest.passed:
            return replace(state, last_processed_ts=ts), None, retest.reason
        plan, reason = build_short_plan(state, rows, cfg)
        if plan is None:
            return (
                replace(
                    state,
                    stage=EventStage.INVALIDATED,
                    last_processed_ts=ts,
                    terminal_reason=reason,
                ),
                None,
                reason,
            )
        return (
            replace(
                state,
                stage=EventStage.PLAN_EMITTED,
                last_processed_ts=ts,
                terminal_reason="one_plan_emitted",
            ),
            plan,
            reason,
        )

    return replace(state, last_processed_ts=ts), None, "unhandled_stage"


def _remember(values: Tuple[str, ...], value: str, limit: int) -> Tuple[str, ...]:
    if value in values:
        return values
    return tuple((values + (value,))[-max(1, int(limit)) :])


def sleeve_step(
    symbol: str,
    closed_rows: Sequence[Sequence[Any]],
    prior: SleeveState,
    cfg: PumpUnwindConfig,
) -> SleeveStep:
    """Pure orchestration with event de-duplication and one-plan invariant."""
    if not closed_rows:
        return SleeveStep(prior, None, "no_rows")
    active = prior.active
    if active is not None and active.stage in TERMINAL_STAGES:
        if _row_ts(closed_rows[-1]) <= active.last_processed_ts:
            return SleeveStep(prior, None, f"terminal:{active.stage.value}")
        active = None

    if active is None:
        detected = detect_expansion_event(symbol, closed_rows, cfg)
        if detected is None:
            return SleeveStep(replace(prior, active=None), None, "no_expansion_event")
        event_id = detected.event.event_id
        if event_id in prior.seen_event_ids:
            return SleeveStep(replace(prior, active=None), None, "event_already_seen")
        new_state = SleeveState(
            active=detected,
            seen_event_ids=_remember(prior.seen_event_ids, event_id, cfg.seen_event_memory),
            planned_event_ids=prior.planned_event_ids,
        )
        return SleeveStep(new_state, None, "event_created")

    new_active, plan, reason = advance_event(active, closed_rows, cfg)
    planned = prior.planned_event_ids
    if plan is not None:
        if plan.event_id in planned:
            plan = None
            reason = "plan_already_emitted"
        else:
            planned = _remember(planned, plan.event_id, cfg.seen_event_memory)
    return SleeveStep(
        SleeveState(
            active=new_active,
            seen_event_ids=prior.seen_event_ids,
            planned_event_ids=planned,
        ),
        plan,
        reason,
    )


class PumpExhaustionUnwindShortV1Strategy:
    """Research adapter.  It is intentionally absent from every live router."""

    STRATEGY_NAME = STRATEGY_NAME
    RESEARCH_ONLY = True
    LIVE_READY = False
    # ``SleeveState`` is intentionally pure/in-memory in this first mechanics
    # version.  A future shadow/live adapter must persist and restore the active
    # FSM plus both event ledgers atomically before it may place any order.
    REQUIRES_PERSISTED_EVENT_STATE = True

    def __init__(self, cfg: Optional[PumpUnwindConfig] = None):
        self.cfg = cfg or PumpUnwindConfig()
        self._states: dict[str, SleeveState] = {}
        self.last_no_signal_reason = ""
        self.last_plan: Optional[PumpUnwindShortPlan] = None

    def process_closed_rows(
        self,
        symbol: str,
        rows: Sequence[Sequence[Any]],
    ) -> Optional[PumpUnwindShortPlan]:
        sym = str(symbol).upper()
        step = sleeve_step(sym, rows, self._states.get(sym, SleeveState()), self.cfg)
        self._states[sym] = step.state
        self.last_no_signal_reason = step.reason
        self.last_plan = step.plan
        return step.plan

    def maybe_signal(
        self,
        store: Any,
        ts_ms: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float = 0.0,
    ) -> Optional[TradeSignal]:
        _ = (open_, high, low, close, volume)
        symbol = str(getattr(store, "symbol", "") or "").upper()
        if not symbol:
            self.last_no_signal_reason = "symbol_missing"
            return None
        raw = store.fetch_klines(
            symbol,
            str(self.cfg.signal_interval_min),
            int(self.cfg.history_limit),
        ) or []
        rows = closed_rows_before(
            raw,
            as_of_ms=int(ts_ms),
            interval_ms=self.cfg.interval_ms,
        )
        plan = self.process_closed_rows(symbol, rows)
        if plan is None:
            return None
        signal = TradeSignal(
            strategy=STRATEGY_NAME,
            symbol=symbol,
            side="short",
            entry=plan.entry_reference,
            sl=plan.stop,
            tp=plan.target_2,
            tps=[plan.target_1, plan.target_2],
            tp_fracs=[0.5, 0.5],
            be_trigger_rr=1.0,
            be_lock_rr=0.1,
            trailing_atr_mult=1.5,
            trail_activate_rr=1.0,
            time_stop_bars=72,
            reason=plan.reason,
        )
        # Research metadata; no execution router consumes this module.
        signal.event_id = plan.event_id
        signal.entry_order_type = plan.entry_type
        signal.valid_from_ts = plan.valid_from_ts
        signal.choch_level = plan.choch_level
        return signal if signal.validate() else None


__all__ = [
    "EventStage",
    "ExhaustionEvidence",
    "FrozenHighLevels",
    "PumpEventState",
    "PumpExpansionEvent",
    "PumpExhaustionUnwindShortV1Strategy",
    "PumpUnwindConfig",
    "PumpUnwindShortPlan",
    "RetestEvidence",
    "SleeveState",
    "SleeveStep",
    "advance_event",
    "bearish_choch",
    "build_short_plan",
    "closed_rows_before",
    "detect_expansion_event",
    "exhaustion_evidence",
    "failed_reclaim_evidence",
    "freeze_pre_event_highs",
    "make_event_id",
    "sleeve_step",
]
