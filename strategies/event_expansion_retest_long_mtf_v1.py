"""Causal MTF successor for the research-only event/retest long sleeve.

Input is one exact, contiguous prefix of *closed* M5 bars plus an explicit
``as_of_ms`` receipt.  Higher timeframes are produced only by
``closed_bar_aggregation_v1``.  The state machine consumes every newly closed
M15 bar in order, so a restart cannot skip an adverse first retest.

This module deliberately has no live adapter, broker route, sizing, fill
model, performance runner, or strategy registry entry.  Plans remain blocked
until execution/cost parity is specified and validated.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple

from bot.closed_bar_aggregation_v1 import (
    ClosedBarAggregationConfigV1,
    ClosedBarAggregationResultV1,
    aggregate_closed_m5_bars,
    canonical_bars_sha256,
)
from bot.level_snapshot_v1 import (
    LevelSnapshotConfigV1,
    LevelSnapshotV1,
    build_resistance_snapshot_v1,
    flip_level_snapshot_v1,
    level_snapshot_from_dict,
    level_snapshot_to_dict,
)
from bot.market_context import atr


M5 = 300_000
M15 = 900_000
H1 = 3_600_000
H4 = 14_400_000
TS, OPEN, HIGH, LOW, CLOSE, VOL = range(6)
STRATEGY_NAME = "event_expansion_retest_long_mtf_v1"
STATE_SCHEMA = "event_expansion_retest_long_mtf_state_v1"
STATE_ENVELOPE_SCHEMA = "event_expansion_retest_long_mtf_state_envelope_v1"
SIDE_IDENTITY = "long_only"


class MTFContractError(ValueError):
    """Evidence/state cannot be interpreted without weakening causality."""


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _is_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _is_id32(value: object) -> bool:
    text = str(value or "")
    return len(text) == 32 and all(c in "0123456789abcdef" for c in text)


def _finite_positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


@dataclass(frozen=True)
class EventExpansionRetestLongMTFConfigV1:
    h1_atr_period: int = 14
    min_h1_history: int = 40
    volume_baseline_h1: int = 24
    min_expansion_range_atr: float = 1.25
    min_expansion_body_fraction: float = 0.45
    min_expansion_return: float = 0.01
    min_volume_multiple: float = 1.25
    breakout_buffer_atr: float = 0.08
    preclose_tolerance_atr: float = 0.20
    max_gap_atr: float = 0.75
    min_respects: int = 2
    min_respect_move_away_atr: float = 0.10
    max_prior_close_overshoot_atr: float = 0.05
    hold_bars_m15: int = 2
    hold_buffer_atr: float = 0.03
    retest_touch_atr: float = 0.10
    max_retest_pierce_atr: float = 0.20
    higher_low_left_bars: int = 1
    higher_low_right_bars: int = 2
    higher_low_min_atr: float = 0.02
    bos_buffer_atr: float = 0.05
    event_expiry_m15: int = 48
    stop_buffer_atr: float = 0.10
    tp1_r: float = 1.0
    tp1_fraction: float = 0.50
    tp2_r: float = 2.0
    tp2_fraction: float = 0.50
    max_hold_m5: int = 96
    level_lookback_bars: int = 120

    def __post_init__(self) -> None:
        positive_ints = (
            "h1_atr_period", "min_h1_history", "volume_baseline_h1",
            "min_respects", "hold_bars_m15", "higher_low_left_bars",
            "higher_low_right_bars", "event_expiry_m15", "max_hold_m5",
            "level_lookback_bars",
        )
        if any(int(getattr(self, name)) <= 0 for name in positive_ints):
            raise MTFContractError("integer configuration fields must be positive")
        if self.min_h1_history < max(self.h1_atr_period + 3, self.volume_baseline_h1 + 2):
            raise MTFContractError("min_h1_history is not causal for its indicators")
        if self.min_respects < 2:
            raise MTFContractError("at least two frozen respects are mandatory")
        for name in (
            "min_expansion_range_atr", "min_expansion_body_fraction",
            "min_expansion_return", "min_volume_multiple", "breakout_buffer_atr",
            "preclose_tolerance_atr", "max_gap_atr", "min_respect_move_away_atr",
            "max_prior_close_overshoot_atr", "hold_buffer_atr", "retest_touch_atr",
            "max_retest_pierce_atr", "higher_low_min_atr", "bos_buffer_atr",
            "stop_buffer_atr",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise MTFContractError(f"{name} must be finite and non-negative")
        if not 0 < self.min_expansion_body_fraction <= 1:
            raise MTFContractError("min_expansion_body_fraction must be in (0,1]")
        # These are part of the v1 frozen research contract, not tuning knobs.
        if (self.tp1_r, self.tp1_fraction, self.tp2_r, self.tp2_fraction, self.max_hold_m5) != (
            1.0, 0.5, 2.0, 0.5, 96,
        ):
            raise MTFContractError("v1 exits must remain 1R/50%, 2R/50%, max_hold=96 M5")

    @property
    def fingerprint(self) -> str:
        return _sha({"strategy": STRATEGY_NAME, "config": asdict(self)})


class MTFStage(str, Enum):
    EXPANDED = "expanded"
    HELD_ABOVE = "held_above"
    FIRST_RETEST_CONSUMED = "first_retest_consumed"
    HIGHER_LOW_CONFIRMED = "higher_low_confirmed"
    PLAN_EMITTED = "plan_emitted"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


TERMINAL = frozenset({MTFStage.PLAN_EMITTED, MTFStage.INVALIDATED, MTFStage.EXPIRED})


@dataclass(frozen=True)
class MTFExpansionEventV1:
    event_id: str
    symbol: str
    side: str
    expansion_open_ts_ms: int
    known_at_ms: int
    h1_atr: float
    level_snapshot: LevelSnapshotV1
    config_sha256: str
    h1_source_sha256: str
    h1_output_sha256: str
    h1_aggregation_config_sha256: str
    provider_fingerprint: str
    expires_at_ms: int

    def __post_init__(self) -> None:
        if self.side != "long" or self.symbol != self.symbol.upper():
            raise MTFContractError("event is physically long-only")
        if self.known_at_ms != self.expansion_open_ts_ms + H1:
            raise MTFContractError("H1 event known_at must be bar open + one hour")
        if self.level_snapshot.symbol != self.symbol or self.level_snapshot.lifecycle != "flip_support":
            raise MTFContractError("event requires its matching flipped level")
        if self.level_snapshot.flipped_at_ms != self.known_at_ms:
            raise MTFContractError("level may flip only when the H1 bar closes")
        if self.level_snapshot.source_end_close_ms > self.expansion_open_ts_ms:
            raise MTFContractError("level source leaks into the H1 expansion")
        if not _finite_positive(self.h1_atr):
            raise MTFContractError("event ATR must be positive")
        if not all(_is_sha(x) for x in (
            self.config_sha256, self.h1_source_sha256, self.h1_output_sha256,
            self.h1_aggregation_config_sha256, self.provider_fingerprint,
        )):
            raise MTFContractError("event provenance is incomplete")
        if not (_is_id32(self.event_id) and _is_id32(self.level_snapshot.level_id)):
            raise MTFContractError("event/level identity is not canonical lowercase hex")
        expected = make_event_id(
            self.symbol, self.expansion_open_ts_ms, self.level_snapshot.snapshot_id,
            self.config_sha256, self.h1_source_sha256, self.h1_output_sha256,
            self.h1_aggregation_config_sha256, self.provider_fingerprint,
        )
        if self.event_id != expected:
            raise MTFContractError("event_id does not bind source/aggregation/level/config")


@dataclass(frozen=True)
class MTFActiveEventStateV1:
    event: MTFExpansionEventV1
    stage: MTFStage
    last_m15_close_ms: int
    hold_count: int = 0
    hold_confirmed_at_ms: Optional[int] = None
    first_retest_id: Optional[str] = None
    first_retest_open_ts_ms: Optional[int] = None
    first_retest_low: Optional[float] = None
    bos_level: Optional[float] = None
    higher_low_open_ts_ms: Optional[int] = None
    higher_low_low: Optional[float] = None
    higher_low_confirmed_at_ms: Optional[int] = None
    emitted_plan_id: Optional[str] = None
    terminal_reason: str = ""


@dataclass(frozen=True)
class MTFResearchPlanV1:
    plan_id: str
    idempotency_key: str
    event_id: str
    level_id: str
    symbol: str
    side: str
    bos_bar_open_ts_ms: int
    known_at_ms: int
    valid_from_m5_open_ts_ms: int
    valid_until_m5_open_ts_ms: int
    entry_reference: float
    stop_price: float
    risk_distance: float
    tp1_price: float
    tp1_fraction: float
    tp2_price: float
    tp2_fraction: float
    max_hold_m5: int
    m15_source_sha256: str
    m15_output_sha256: str
    m15_aggregation_config_sha256: str
    config_sha256: str
    executable: bool = False
    preflight_status: str = "BLOCKED_EXECUTION_COST_MODEL"

    def __post_init__(self) -> None:
        if self.side != "long" or self.symbol != self.symbol.upper():
            raise MTFContractError("plan is physically long-only")
        if self.known_at_ms != self.bos_bar_open_ts_ms + M15:
            raise MTFContractError("M15 BOS known_at must be bar open + 15 minutes")
        if self.valid_from_m5_open_ts_ms != self.known_at_ms:
            raise MTFContractError("the exact next M5 open equals BOS known_at")
        if self.valid_until_m5_open_ts_ms != self.valid_from_m5_open_ts_ms + M5:
            raise MTFContractError("research plan may target one exact M5 open only")
        if not (0 < self.stop_price < self.entry_reference):
            raise MTFContractError("long stop/reference geometry is invalid")
        risk = self.entry_reference - self.stop_price
        if not math.isclose(self.risk_distance, risk, rel_tol=1e-12, abs_tol=1e-12):
            raise MTFContractError("risk distance is not frozen from reference/stop")
        if not math.isclose(self.tp1_price, self.entry_reference + risk, rel_tol=1e-12):
            raise MTFContractError("TP1 must be exactly 1R")
        if not math.isclose(self.tp2_price, self.entry_reference + 2 * risk, rel_tol=1e-12):
            raise MTFContractError("TP2 must be exactly 2R")
        if (self.tp1_fraction, self.tp2_fraction, self.max_hold_m5) != (0.5, 0.5, 96):
            raise MTFContractError("v1 exit fractions/hold are frozen")
        if self.executable or self.preflight_status != "BLOCKED_EXECUTION_COST_MODEL":
            raise MTFContractError("MTF v1 plan is research-only")
        if not all(_is_sha(value) for value in (
            self.m15_source_sha256, self.m15_output_sha256,
            self.m15_aggregation_config_sha256, self.config_sha256,
        )):
            raise MTFContractError("plan source/aggregation/config provenance is incomplete")
        if not all(_is_id32(value) for value in (
            self.plan_id, self.idempotency_key, self.event_id, self.level_id,
        )):
            raise MTFContractError("plan identities must be canonical lowercase hex")
        expected = make_plan_id(
            self.event_id, self.level_id, self.bos_bar_open_ts_ms,
            self.m15_source_sha256, self.m15_output_sha256,
            self.m15_aggregation_config_sha256, self.config_sha256,
        )
        if self.plan_id != expected or self.idempotency_key != expected:
            raise MTFContractError("plan identity does not bind its evidence")


@dataclass(frozen=True)
class MTFOrchestratorStateV1:
    schema: str
    strategy: str
    symbol: str
    side_identity: str
    provider_identity: str
    provider_fingerprint: str
    config_sha256: str
    aggregation_config_fingerprints: Tuple[Tuple[str, str], ...]
    source_start_open_ts_ms: int
    source_count: int
    source_sha256: str
    m5_watermark_close_ms: int
    m15_watermark_close_ms: int
    h1_watermark_close_ms: int
    active: Optional[MTFActiveEventStateV1]
    seen_event_ids: Tuple[str, ...]
    consumed_retest_ids: Tuple[str, ...]
    plan_outbox: Tuple[MTFResearchPlanV1, ...]
    acknowledged_plan_ids: Tuple[str, ...]


@dataclass(frozen=True)
class MTFOrchestratorStepV1:
    state: MTFOrchestratorStateV1
    plan: Optional[MTFResearchPlanV1]
    reason: str


def make_event_id(symbol: str, expansion_open_ts_ms: int, snapshot_id: str,
                  config_sha: str, source_sha: str, output_sha: str,
                  aggregation_sha: str, provider_sha: str) -> str:
    return _sha({
        "strategy": STRATEGY_NAME, "side": "long", "symbol": symbol,
        "expansion_open_ts_ms": expansion_open_ts_ms, "snapshot_id": snapshot_id,
        "config_sha256": config_sha, "h1_source_sha256": source_sha,
        "h1_output_sha256": output_sha,
        "h1_aggregation_config_sha256": aggregation_sha,
        "provider_fingerprint": provider_sha,
    })[:32]


def make_plan_id(event_id: str, level_id: str, bos_open_ts_ms: int,
                 source_sha: str, output_sha: str, aggregation_sha: str,
                 config_sha: str) -> str:
    return _sha({
        "strategy": STRATEGY_NAME, "side": "long", "event_id": event_id,
        "level_id": level_id, "bos_bar_open_ts_ms": bos_open_ts_ms,
        "m15_source_sha256": source_sha, "m15_output_sha256": output_sha,
        "m15_aggregation_config_sha256": aggregation_sha,
        "config_sha256": config_sha,
    })[:32]


def _aggregation_fingerprints() -> Tuple[Tuple[str, str], ...]:
    return tuple((tf, ClosedBarAggregationConfigV1(target_timeframe=tf).fingerprint)
                 for tf in ("M15", "H1", "H4"))


def _validate_raw_m5(rows: Sequence[Sequence[Any]], *, as_of_ms: int) -> tuple[tuple, str]:
    if not rows or isinstance(rows, (str, bytes)):
        raise MTFContractError("raw closed M5 prefix must be non-empty")
    if isinstance(as_of_ms, bool) or not isinstance(as_of_ms, int) or as_of_ms % M5:
        raise MTFContractError("as_of_ms must be an explicit M5 boundary")
    canonical_bars_sha256(rows)  # strict OHLCV/numeric validation from the shared contract
    normalized = tuple(tuple(row) for row in rows)
    previous = None
    for index, row in enumerate(normalized):
        ts = row[TS]
        if isinstance(ts, bool) or not isinstance(ts, int) or ts % M5:
            raise MTFContractError(f"row {index} timestamp is not canonical M5")
        if previous is not None and ts - previous != M5:
            raise MTFContractError("raw M5 prefix contains a gap/disorder")
        previous = ts
    if normalized[0][TS] % H4:
        raise MTFContractError("v1 raw source must start on an H4 UTC boundary")
    if normalized[-1][TS] + M5 != as_of_ms:
        raise MTFContractError("receipt must end at the exact final M5 close; open/future tails forbidden")
    return normalized, canonical_bars_sha256(normalized)


def _aggregate_to(rows: Sequence[Sequence[Any]], *, boundary_ms: int, timeframe: str,
                  provider_identity: str, provider_fingerprint: str) -> Optional[ClosedBarAggregationResultV1]:
    interval = {"M15": M15, "H1": H1, "H4": H4}[timeframe]
    if boundary_ms % interval:
        raise MTFContractError(f"{timeframe} aggregation boundary is off-grid")
    subset = [row for row in rows if int(row[TS]) + M5 <= boundary_ms]
    if not subset:
        return None
    return aggregate_closed_m5_bars(
        subset, as_of_ms=boundary_ms, provider_identity=provider_identity,
        provider_fingerprint=provider_fingerprint,
        config=ClosedBarAggregationConfigV1(target_timeframe=timeframe),
    )


def _strict_level_eligible(snapshot: LevelSnapshotV1, pre_bars: Sequence[Sequence[Any]],
                           cfg: EventExpansionRetestLongMTFConfigV1) -> bool:
    if len(snapshot.respect_history) < cfg.min_respects:
        return False
    if any(item.move_away_atr < cfg.min_respect_move_away_atr
           for item in snapshot.respect_history):
        return False
    # Phase-0's level builder does not yet encode an explicit unbroken flag;
    # this successor therefore independently vetoes an earlier close-through.
    for row in pre_bars:
        close_time = int(row[TS]) + snapshot.interval_ms
        if close_time <= snapshot.valid_at_ms:
            continue
        if float(row[CLOSE]) > snapshot.zone_high + cfg.max_prior_close_overshoot_atr * snapshot.atr_at_creation:
            return False
    return True


def _build_level(symbol: str, timeframe: str, receipt: Optional[ClosedBarAggregationResultV1],
                 *, expansion_open_ts_ms: int, provider_fingerprint: str,
                 cfg: EventExpansionRetestLongMTFConfigV1) -> Optional[LevelSnapshotV1]:
    if receipt is None or receipt.target_timeframe != timeframe:
        return None
    if receipt.source_end_close_ts_ms > expansion_open_ts_ms or receipt.as_of_ms > expansion_open_ts_ms:
        raise MTFContractError("level aggregation leaks into expansion bar")
    level_cfg = LevelSnapshotConfigV1(
        lookback_bars=cfg.level_lookback_bars,
        max_distance_atr=5.0,
    )
    snapshot = build_resistance_snapshot_v1(
        symbol, timeframe, receipt.output_bars,
        as_of_ms=expansion_open_ts_ms,
        provider_fingerprint=provider_fingerprint, cfg=level_cfg,
        aggregation_result=receipt,
    )
    if snapshot is None or snapshot.source_end_close_ms > expansion_open_ts_ms:
        return None
    return snapshot if _strict_level_eligible(snapshot, receipt.output_bars, cfg) else None


def _detect_h1_event(symbol: str, h1_receipt: ClosedBarAggregationResultV1,
                     h1_index: int, raw_rows: Sequence[Sequence[Any]],
                     provider_identity: str, provider_fingerprint: str,
                     cfg: EventExpansionRetestLongMTFConfigV1) -> Optional[MTFExpansionEventV1]:
    bars = h1_receipt.output_bars[:h1_index + 1]
    if len(bars) < cfg.min_h1_history:
        return None
    pre, bar = bars[:-1], bars[-1]
    a = atr(pre, cfg.h1_atr_period)
    if not _finite_positive(a):
        return None
    o, h, low, close, volume = (float(bar[i]) for i in (OPEN, HIGH, LOW, CLOSE, VOL))
    bar_range = h - low
    baseline = [float(row[VOL]) for row in pre[-cfg.volume_baseline_h1:]]
    prior_close = float(pre[-1][CLOSE])
    if not (
        close > o and bar_range / a >= cfg.min_expansion_range_atr
        and (close - o) / max(bar_range, 1e-12) >= cfg.min_expansion_body_fraction
        and (close - prior_close) / prior_close >= cfg.min_expansion_return
        and baseline and sum(baseline) / len(baseline) > 0
        and volume / (sum(baseline) / len(baseline)) >= cfg.min_volume_multiple
    ):
        return None
    expansion_open = int(bar[TS])
    known_at = expansion_open + H1
    pre_h1 = _aggregate_to(
        raw_rows, boundary_ms=expansion_open, timeframe="H1",
        provider_identity=provider_identity, provider_fingerprint=provider_fingerprint,
    )
    h4_boundary = expansion_open - (expansion_open % H4)
    pre_h4 = _aggregate_to(
        raw_rows, boundary_ms=h4_boundary, timeframe="H4",
        provider_identity=provider_identity, provider_fingerprint=provider_fingerprint,
    ) if h4_boundary > int(raw_rows[0][TS]) else None
    levels = [item for item in (
        _build_level(symbol, "H1", pre_h1, expansion_open_ts_ms=expansion_open,
                     provider_fingerprint=provider_fingerprint, cfg=cfg),
        _build_level(symbol, "H4", pre_h4, expansion_open_ts_ms=expansion_open,
                     provider_fingerprint=provider_fingerprint, cfg=cfg),
    ) if item is not None]
    eligible = [item for item in levels if (
        prior_close <= item.zone_high + cfg.preclose_tolerance_atr * a
        and close > item.zone_high + cfg.breakout_buffer_atr * a
        and o <= item.zone_high + cfg.max_gap_atr * a
    )]
    if not eligible:
        return None
    level = min(eligible, key=lambda item: (
        abs(item.zone_high - prior_close), 0 if item.timeframe == "H4" else 1,
    ))
    flipped = flip_level_snapshot_v1(level, breakout_ts_ms=known_at, breakout_close=close)
    exact_h1 = _aggregate_to(
        raw_rows, boundary_ms=known_at, timeframe="H1",
        provider_identity=provider_identity, provider_fingerprint=provider_fingerprint,
    )
    if exact_h1 is None:
        raise MTFContractError("missing H1 aggregation receipt at event close")
    event_id = make_event_id(
        symbol, expansion_open, level.snapshot_id, cfg.fingerprint,
        exact_h1.source_sha256, exact_h1.output_sha256,
        exact_h1.config_fingerprint, provider_fingerprint,
    )
    return MTFExpansionEventV1(
        event_id=event_id, symbol=symbol, side="long",
        expansion_open_ts_ms=expansion_open, known_at_ms=known_at, h1_atr=float(a),
        level_snapshot=flipped, config_sha256=cfg.fingerprint,
        h1_source_sha256=exact_h1.source_sha256,
        h1_output_sha256=exact_h1.output_sha256,
        h1_aggregation_config_sha256=exact_h1.config_fingerprint,
        provider_fingerprint=provider_fingerprint,
        expires_at_ms=known_at + cfg.event_expiry_m15 * M15,
    )


def _retest_id(event_id: str, bar_open_ts: int, receipt: ClosedBarAggregationResultV1) -> str:
    return _sha({"event_id": event_id, "bar_open_ts": bar_open_ts,
                 "source": receipt.source_sha256, "output": receipt.output_sha256})[:32]


def _advance(active: MTFActiveEventStateV1, bars: Sequence[Sequence[Any]], index: int,
             receipt: ClosedBarAggregationResultV1,
             cfg: EventExpansionRetestLongMTFConfigV1
             ) -> tuple[MTFActiveEventStateV1, Optional[MTFResearchPlanV1], Optional[str], str]:
    bar = bars[index]
    open_ts, known_at = int(bar[TS]), int(bar[TS]) + M15
    if known_at != active.last_m15_close_ms + M15:
        raise MTFContractError("M15 replay skipped a bar after persisted watermark")
    if known_at > active.event.expires_at_ms:
        return replace(active, stage=MTFStage.EXPIRED, last_m15_close_ms=known_at,
                       terminal_reason="event_expiry"), None, None, "event_expired"
    level, a = active.event.level_snapshot, active.event.h1_atr
    o, high, low, close = (float(bar[i]) for i in (OPEN, HIGH, LOW, CLOSE))
    if active.stage not in {MTFStage.EXPANDED, MTFStage.HELD_ABOVE} and close < level.zone_low:
        return replace(active, stage=MTFStage.INVALIDATED, last_m15_close_ms=known_at,
                       terminal_reason="flip_close_failed"), None, None, "flip_close_failed"

    if active.stage == MTFStage.EXPANDED:
        if low <= level.zone_high + cfg.retest_touch_atr * a:
            rid = _retest_id(active.event.event_id, open_ts, receipt)
            return replace(
                active, stage=MTFStage.INVALIDATED, last_m15_close_ms=known_at,
                first_retest_id=rid, first_retest_open_ts_ms=open_ts,
                first_retest_low=low, terminal_reason="first_retest_before_hold",
            ), None, rid, "first_retest_before_hold"
        count = active.hold_count + 1 if close >= level.zone_high + cfg.hold_buffer_atr * a else 0
        if count >= cfg.hold_bars_m15:
            return replace(active, stage=MTFStage.HELD_ABOVE,
                           last_m15_close_ms=known_at, hold_count=count,
                           hold_confirmed_at_ms=known_at), None, None, "hold_confirmed"
        return replace(active, last_m15_close_ms=known_at, hold_count=count), None, None, "holding"

    if active.stage == MTFStage.HELD_ABOVE:
        if low > level.zone_high + cfg.retest_touch_atr * a:
            return replace(active, last_m15_close_ms=known_at), None, None, "waiting_first_retest"
        rid = _retest_id(active.event.event_id, open_ts, receipt)
        if low < level.zone_low - cfg.max_retest_pierce_atr * a or close < level.level:
            return replace(
                active, stage=MTFStage.INVALIDATED, last_m15_close_ms=known_at,
                first_retest_id=rid, first_retest_open_ts_ms=open_ts,
                first_retest_low=low, terminal_reason="first_retest_failed",
            ), None, rid, "first_retest_failed"
        earlier = [row for row in bars if active.event.known_at_ms < int(row[TS]) + M15 < known_at]
        if not earlier:
            raise MTFContractError("retest lacks a strictly earlier M15 structure reference")
        return replace(
            active, stage=MTFStage.FIRST_RETEST_CONSUMED,
            last_m15_close_ms=known_at, first_retest_id=rid,
            first_retest_open_ts_ms=open_ts, first_retest_low=low,
            bos_level=max(float(row[HIGH]) for row in earlier),
        ), None, rid, "first_retest_consumed"

    if active.stage == MTFStage.FIRST_RETEST_CONSUMED:
        assert active.first_retest_open_ts_ms is not None and active.first_retest_low is not None
        retest_index = next((i for i, row in enumerate(bars)
                             if int(row[TS]) == active.first_retest_open_ts_ms), -1)
        if retest_index < 0:
            raise MTFContractError("persisted first retest is absent from aggregation prefix")
        if low <= active.first_retest_low:
            return replace(active, stage=MTFStage.INVALIDATED,
                           last_m15_close_ms=known_at,
                           terminal_reason="retest_low_broken"), None, None, "retest_low_broken"
        candidate_index = index - cfg.higher_low_right_bars
        if candidate_index - cfg.higher_low_left_bars <= retest_index:
            return replace(active, last_m15_close_ms=known_at), None, None, "waiting_distinct_higher_low"
        candidate = bars[candidate_index]
        candidate_low = float(candidate[LOW])
        left = bars[candidate_index - cfg.higher_low_left_bars:candidate_index]
        right = bars[candidate_index + 1:index + 1]
        pivot = bool(
            len(right) == cfg.higher_low_right_bars
            and candidate_low < min(float(row[LOW]) for row in left)
            and candidate_low < min(float(row[LOW]) for row in right)
            and candidate_low > active.first_retest_low + cfg.higher_low_min_atr * a
        )
        if not pivot:
            return replace(active, last_m15_close_ms=known_at), None, None, "waiting_distinct_higher_low"
        return replace(
            active, stage=MTFStage.HIGHER_LOW_CONFIRMED,
            last_m15_close_ms=known_at,
            higher_low_open_ts_ms=int(candidate[TS]), higher_low_low=candidate_low,
            higher_low_confirmed_at_ms=known_at,
        ), None, None, "higher_low_confirmed"

    if active.stage == MTFStage.HIGHER_LOW_CONFIRMED:
        assert active.higher_low_confirmed_at_ms is not None and active.bos_level is not None
        if known_at <= active.higher_low_confirmed_at_ms:
            raise MTFContractError("BOS cannot share the higher-low confirmation bar")
        threshold = active.bos_level + cfg.bos_buffer_atr * a
        previous_close = float(bars[index - 1][CLOSE])
        if not (previous_close <= threshold and close > threshold and close > o):
            return replace(active, last_m15_close_ms=known_at), None, None, "waiting_later_bullish_bos"
        stop = min(float(active.first_retest_low), level.zone_low) - cfg.stop_buffer_atr * a
        if stop <= 0 or stop >= close:
            return replace(active, stage=MTFStage.INVALIDATED,
                           last_m15_close_ms=known_at,
                           terminal_reason="risk_geometry_invalid"), None, None, "risk_geometry_invalid"
        risk = close - stop
        plan_id = make_plan_id(
            active.event.event_id, level.level_id, open_ts,
            receipt.source_sha256, receipt.output_sha256,
            receipt.config_fingerprint, cfg.fingerprint,
        )
        plan = MTFResearchPlanV1(
            plan_id=plan_id, idempotency_key=plan_id,
            event_id=active.event.event_id, level_id=level.level_id,
            symbol=active.event.symbol, side="long", bos_bar_open_ts_ms=open_ts,
            known_at_ms=known_at, valid_from_m5_open_ts_ms=known_at,
            valid_until_m5_open_ts_ms=known_at + M5,
            entry_reference=close, stop_price=stop, risk_distance=risk,
            tp1_price=close + risk, tp1_fraction=0.5,
            tp2_price=close + 2 * risk, tp2_fraction=0.5, max_hold_m5=96,
            m15_source_sha256=receipt.source_sha256,
            m15_output_sha256=receipt.output_sha256,
            m15_aggregation_config_sha256=receipt.config_fingerprint,
            config_sha256=cfg.fingerprint,
        )
        return replace(active, stage=MTFStage.PLAN_EMITTED,
                       last_m15_close_ms=known_at,
                       emitted_plan_id=plan_id,
                       terminal_reason="one_plan_to_atomic_outbox"), plan, None, "plan_ready"
    return replace(active, last_m15_close_ms=known_at), None, None, "terminal"


def process_closed_m5_prefix(
    symbol: str, raw_closed_m5: Sequence[Sequence[Any]], *, as_of_ms: int,
    provider_identity: str, provider_fingerprint: str,
    prior: Optional[MTFOrchestratorStateV1] = None,
    cfg: Optional[EventExpansionRetestLongMTFConfigV1] = None,
) -> MTFOrchestratorStepV1:
    """Replay every new M15 receipt and atomically enqueue at most one plan/event."""
    config = cfg or EventExpansionRetestLongMTFConfigV1()
    canonical_symbol = str(symbol or "")
    if not canonical_symbol or canonical_symbol != canonical_symbol.upper():
        raise MTFContractError("symbol must already be canonical uppercase")
    if not _is_sha(provider_fingerprint):
        raise MTFContractError("provider_fingerprint must be lowercase SHA256")
    rows, full_source_sha = _validate_raw_m5(raw_closed_m5, as_of_ms=as_of_ms)
    fps = _aggregation_fingerprints()
    if prior is not None:
        _validate_state(prior)
        if (prior.symbol, prior.provider_identity, prior.provider_fingerprint,
            prior.config_sha256, prior.aggregation_config_fingerprints) != (
            canonical_symbol, provider_identity, provider_fingerprint,
            config.fingerprint, fps,
        ):
            raise MTFContractError("persisted source/config/provider/timeframe pins mismatch")
        if len(rows) < prior.source_count:
            raise MTFContractError("source prefix was truncated after restart")
        if canonical_bars_sha256(rows[:prior.source_count]) != prior.source_sha256:
            raise MTFContractError("historical M5 prefix changed after restart")
        if prior.source_start_open_ts_ms != int(rows[0][TS]):
            raise MTFContractError("source start changed after restart")
        if prior.m5_watermark_close_ms > as_of_ms:
            raise MTFContractError("as_of moved behind persisted M5 watermark")
        start_boundary = prior.m15_watermark_close_ms
        active, seen = prior.active, prior.seen_event_ids
        consumed, outbox, acked = prior.consumed_retest_ids, prior.plan_outbox, prior.acknowledged_plan_ids
    else:
        start_boundary = int(rows[0][TS])
        active, seen, consumed, outbox, acked = None, (), (), (), ()

    m15_end = as_of_ms - (as_of_ms % M15)
    h1_end = as_of_ms - (as_of_ms % H1)
    m15_receipt = _aggregate_to(
        rows, boundary_ms=m15_end, timeframe="M15",
        provider_identity=provider_identity, provider_fingerprint=provider_fingerprint,
    ) if m15_end > int(rows[0][TS]) else None
    h1_receipt = _aggregate_to(
        rows, boundary_ms=h1_end, timeframe="H1",
        provider_identity=provider_identity, provider_fingerprint=provider_fingerprint,
    ) if h1_end > int(rows[0][TS]) else None
    latest_plan = None
    reason = "no_new_complete_m15"
    if m15_receipt is not None:
        h1_by_close = ({int(bar[TS]) + H1: i for i, bar in enumerate(h1_receipt.output_bars)}
                       if h1_receipt is not None else {})
        for index, bar in enumerate(m15_receipt.output_bars):
            boundary = int(bar[TS]) + M15
            if boundary <= start_boundary:
                continue
            if active is not None and active.stage in TERMINAL:
                active = None
            if active is None and boundary in h1_by_close:
                event = _detect_h1_event(
                    canonical_symbol, h1_receipt, h1_by_close[boundary], rows,
                    provider_identity, provider_fingerprint, config,
                )
                if event is not None and event.event_id not in seen:
                    active = MTFActiveEventStateV1(
                        event=event, stage=MTFStage.EXPANDED,
                        last_m15_close_ms=boundary,
                    )
                    seen = seen + (event.event_id,)
                    reason = "event_created"
                    continue  # the expansion's final M15 cannot also be a hold/retest
            if active is not None and boundary > active.event.known_at_ms:
                exact_receipt = _aggregate_to(
                    rows, boundary_ms=boundary, timeframe="M15",
                    provider_identity=provider_identity,
                    provider_fingerprint=provider_fingerprint,
                )
                if exact_receipt is None:
                    raise MTFContractError("missing exact M15 receipt during replay")
                active, plan, retest_id, reason = _advance(
                    active, m15_receipt.output_bars[:index + 1], index,
                    exact_receipt, config,
                )
                if retest_id is not None:
                    if retest_id in consumed:
                        raise MTFContractError("first retest receipt was consumed twice")
                    consumed = consumed + (retest_id,)
                if plan is not None:
                    if any(item.plan_id == plan.plan_id for item in outbox) or plan.plan_id in acked:
                        raise MTFContractError("plan idempotency key already exists")
                    outbox = outbox + (plan,)  # returned in the same immutable state transition
                    latest_plan = plan

    state = MTFOrchestratorStateV1(
        schema=STATE_SCHEMA, strategy=STRATEGY_NAME, symbol=canonical_symbol,
        side_identity=SIDE_IDENTITY, provider_identity=provider_identity,
        provider_fingerprint=provider_fingerprint, config_sha256=config.fingerprint,
        aggregation_config_fingerprints=fps,
        source_start_open_ts_ms=int(rows[0][TS]), source_count=len(rows),
        source_sha256=full_source_sha, m5_watermark_close_ms=as_of_ms,
        m15_watermark_close_ms=m15_end, h1_watermark_close_ms=h1_end,
        active=active, seen_event_ids=seen, consumed_retest_ids=consumed,
        plan_outbox=outbox, acknowledged_plan_ids=acked,
    )
    _validate_state(state)
    return MTFOrchestratorStepV1(state, latest_plan, reason)


def _event_to_obj(event: MTFExpansionEventV1) -> dict[str, Any]:
    obj = asdict(event)
    obj["level_snapshot"] = level_snapshot_to_dict(event.level_snapshot)
    return obj


def _event_from_obj(obj: Mapping[str, Any]) -> MTFExpansionEventV1:
    data = dict(obj)
    data["level_snapshot"] = level_snapshot_from_dict(data["level_snapshot"])
    return MTFExpansionEventV1(**data)


def _active_to_obj(active: Optional[MTFActiveEventStateV1]) -> Optional[dict[str, Any]]:
    if active is None:
        return None
    obj = asdict(active)
    obj["event"] = _event_to_obj(active.event)
    obj["stage"] = active.stage.value
    return obj


def _active_from_obj(obj: Optional[Mapping[str, Any]]) -> Optional[MTFActiveEventStateV1]:
    if obj is None:
        return None
    data = dict(obj)
    data["event"] = _event_from_obj(data["event"])
    data["stage"] = MTFStage(data["stage"])
    return MTFActiveEventStateV1(**data)


def _state_payload(state: MTFOrchestratorStateV1) -> dict[str, Any]:
    return {
        "schema": state.schema, "strategy": state.strategy, "symbol": state.symbol,
        "side_identity": state.side_identity, "provider_identity": state.provider_identity,
        "provider_fingerprint": state.provider_fingerprint,
        "config_sha256": state.config_sha256,
        "aggregation_config_fingerprints": [list(x) for x in state.aggregation_config_fingerprints],
        "source_start_open_ts_ms": state.source_start_open_ts_ms,
        "source_count": state.source_count, "source_sha256": state.source_sha256,
        "m5_watermark_close_ms": state.m5_watermark_close_ms,
        "m15_watermark_close_ms": state.m15_watermark_close_ms,
        "h1_watermark_close_ms": state.h1_watermark_close_ms,
        "active": _active_to_obj(state.active),
        "seen_event_ids": list(state.seen_event_ids),
        "consumed_retest_ids": list(state.consumed_retest_ids),
        "plan_outbox": [asdict(item) for item in state.plan_outbox],
        "acknowledged_plan_ids": list(state.acknowledged_plan_ids),
    }


def state_to_json(state: MTFOrchestratorStateV1) -> str:
    _validate_state(state)
    payload = _state_payload(state)
    envelope = {"schema": STATE_ENVELOPE_SCHEMA, "payload": payload,
                "payload_sha256": _sha(payload)}
    return json.dumps(envelope, sort_keys=True, indent=2, allow_nan=False) + "\n"


def state_from_json(text: str, *, expected_provider_fingerprint: str,
                    expected_cfg: EventExpansionRetestLongMTFConfigV1
                    ) -> MTFOrchestratorStateV1:
    try:
        envelope = json.loads(text)
        if set(envelope) != {"schema", "payload", "payload_sha256"}:
            raise MTFContractError("state envelope keys mismatch")
        if envelope["schema"] != STATE_ENVELOPE_SCHEMA or envelope["payload_sha256"] != _sha(envelope["payload"]):
            raise MTFContractError("state envelope schema/checksum mismatch")
        obj = envelope["payload"]
        state = MTFOrchestratorStateV1(
            schema=obj["schema"], strategy=obj["strategy"], symbol=obj["symbol"],
            side_identity=obj["side_identity"], provider_identity=obj["provider_identity"],
            provider_fingerprint=obj["provider_fingerprint"], config_sha256=obj["config_sha256"],
            aggregation_config_fingerprints=tuple(tuple(x) for x in obj["aggregation_config_fingerprints"]),
            source_start_open_ts_ms=int(obj["source_start_open_ts_ms"]),
            source_count=int(obj["source_count"]), source_sha256=obj["source_sha256"],
            m5_watermark_close_ms=int(obj["m5_watermark_close_ms"]),
            m15_watermark_close_ms=int(obj["m15_watermark_close_ms"]),
            h1_watermark_close_ms=int(obj["h1_watermark_close_ms"]),
            active=_active_from_obj(obj["active"]),
            seen_event_ids=tuple(obj["seen_event_ids"]),
            consumed_retest_ids=tuple(obj["consumed_retest_ids"]),
            plan_outbox=tuple(MTFResearchPlanV1(**item) for item in obj["plan_outbox"]),
            acknowledged_plan_ids=tuple(obj["acknowledged_plan_ids"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, MTFContractError):
            raise
        raise MTFContractError(f"invalid persisted MTF state: {exc}") from exc
    _validate_state(state)
    if state.provider_fingerprint != expected_provider_fingerprint or state.config_sha256 != expected_cfg.fingerprint:
        raise MTFContractError("persisted provider/config mismatch")
    return state


def acknowledge_plan(state: MTFOrchestratorStateV1, plan_id: str) -> MTFOrchestratorStateV1:
    matches = tuple(item for item in state.plan_outbox if item.plan_id == plan_id)
    if len(matches) != 1 or plan_id in state.acknowledged_plan_ids:
        raise MTFContractError("plan acknowledgement is missing or duplicate")
    updated = replace(
        state, plan_outbox=tuple(item for item in state.plan_outbox if item.plan_id != plan_id),
        acknowledged_plan_ids=state.acknowledged_plan_ids + (plan_id,),
    )
    _validate_state(updated)
    return updated


def _validate_state(state: MTFOrchestratorStateV1) -> None:
    if (state.schema, state.strategy, state.side_identity) != (STATE_SCHEMA, STRATEGY_NAME, SIDE_IDENTITY):
        raise MTFContractError("state schema/strategy/side mismatch")
    if state.symbol != state.symbol.upper() or not _is_sha(state.provider_fingerprint):
        raise MTFContractError("state symbol/provider is invalid")
    if state.aggregation_config_fingerprints != _aggregation_fingerprints():
        raise MTFContractError("state aggregation timeframe/config mismatch")
    if not (_is_sha(state.config_sha256) and _is_sha(state.source_sha256)):
        raise MTFContractError("state source/config hash is invalid")
    if state.source_count <= 0 or state.m5_watermark_close_ms <= state.source_start_open_ts_ms:
        raise MTFContractError("state source watermarks are invalid")
    if (
        state.source_start_open_ts_ms % H4
        or state.m5_watermark_close_ms % M5
        or state.m15_watermark_close_ms % M15
        or state.h1_watermark_close_ms % H1
    ):
        raise MTFContractError("state watermarks are off their canonical grids")
    if state.m15_watermark_close_ms != state.m5_watermark_close_ms - state.m5_watermark_close_ms % M15:
        raise MTFContractError("M15 watermark is not the exact floor of the M5 receipt")
    if state.h1_watermark_close_ms != state.m5_watermark_close_ms - state.m5_watermark_close_ms % H1:
        raise MTFContractError("H1 watermark is not the exact floor of the M5 receipt")
    if state.source_count * M5 != state.m5_watermark_close_ms - state.source_start_open_ts_ms:
        raise MTFContractError("state source count/span does not match its M5 watermark")
    for values, name in (
        (state.seen_event_ids, "seen events"),
        (state.consumed_retest_ids, "consumed retests"),
        (state.acknowledged_plan_ids, "acknowledged plans"),
    ):
        if len(values) != len(set(values)):
            raise MTFContractError(f"state {name} contain duplicates")
        if not all(_is_id32(value) for value in values):
            raise MTFContractError(f"state {name} must be canonical 32-character lowercase hex")
    outbox_ids = tuple(item.plan_id for item in state.plan_outbox)
    if len(outbox_ids) != len(set(outbox_ids)) or set(outbox_ids) & set(state.acknowledged_plan_ids):
        raise MTFContractError("state plan outbox/idempotency ledger is inconsistent")
    for plan in state.plan_outbox:
        if plan.symbol != state.symbol or plan.config_sha256 != state.config_sha256:
            raise MTFContractError("outbox plan does not match outer state symbol/config")
        if plan.event_id not in state.seen_event_ids:
            raise MTFContractError("outbox plan event is absent from durable seen ledger")
        if plan.known_at_ms > state.m15_watermark_close_ms:
            raise MTFContractError("outbox plan lies beyond the persisted M15 watermark")
    if state.active is not None:
        if (
            state.active.event.symbol != state.symbol
            or state.active.event.provider_fingerprint != state.provider_fingerprint
            or state.active.event.config_sha256 != state.config_sha256
        ):
            raise MTFContractError("active event does not match outer state symbol/provider/config")
        if (
            state.active.last_m15_close_ms % M15
            or state.active.last_m15_close_ms < state.active.event.known_at_ms
            or state.active.last_m15_close_ms > state.m15_watermark_close_ms
        ):
            raise MTFContractError("active M15 watermark is unaligned or outside outer state")
        if state.active.event.event_id not in state.seen_event_ids:
            raise MTFContractError("active event is absent from durable seen ledger")
        if state.active.first_retest_id is not None and state.active.first_retest_id not in state.consumed_retest_ids:
            raise MTFContractError("active first retest is absent from durable consumed ledger")
        if state.active.stage == MTFStage.PLAN_EMITTED:
            plan_id = state.active.emitted_plan_id
            if not plan_id or not (
                any(item.plan_id == plan_id and item.event_id == state.active.event.event_id
                    for item in state.plan_outbox)
                or plan_id in state.acknowledged_plan_ids
            ):
                raise MTFContractError("emitted event has no matching durable event-to-plan receipt")
        elif state.active.emitted_plan_id is not None:
            raise MTFContractError("non-emitted event carries an emitted_plan_id")


class EventExpansionRetestLongMTFV1Research:
    RESEARCH_ONLY = True
    LIVE_READY = False
    PERFORMANCE_READY = False
    SIDE_IDENTITY = SIDE_IDENTITY
    REQUIRES_ATOMIC_STATE_AND_OUTBOX_PERSISTENCE = True


__all__ = [
    "EventExpansionRetestLongMTFConfigV1", "EventExpansionRetestLongMTFV1Research",
    "MTFActiveEventStateV1", "MTFContractError", "MTFExpansionEventV1",
    "MTFOrchestratorStateV1", "MTFOrchestratorStepV1", "MTFResearchPlanV1",
    "MTFStage", "SIDE_IDENTITY", "STATE_SCHEMA", "STRATEGY_NAME",
    "acknowledge_plan", "make_event_id", "make_plan_id",
    "process_closed_m5_prefix", "state_from_json", "state_to_json",
]
