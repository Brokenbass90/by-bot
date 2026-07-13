"""Fail-closed research bridge from the MTF event sleeve to execution v1.

The MTF orchestrator intentionally emits a non-executable research plan.  The
execution simulator intentionally accepts only its own immutable
``FrozenLongPlanV1``.  This module is the narrow evidence bridge between those
contracts.  It does not acknowledge the MTF outbox, read files, fetch market
data, route an order, size a position, or make a performance claim.

Conversion is permitted only at the exact M15 close / next-M5-open boundary
and only while the exact MTF plan remains in the validated atomic outbox.  A
deterministic receipt binds the complete outer state, MTF plan, expansion
event, flipped level, raw M5 prefix, and H1/M15 aggregation identities.  That
receipt fingerprint becomes the execution plan's source fingerprint; the MTF
and execution plan identifiers consequently remain distinct identities.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Tuple

from bot.event_long_execution_v1 import (
    FrozenLongPlanV1,
    make_frozen_long_plan_v1,
)
from bot.level_snapshot_v1 import level_snapshot_to_dict
from strategies.event_expansion_retest_long_mtf_v1 import (
    M5,
    M15,
    SIDE_IDENTITY,
    STRATEGY_NAME,
    MTFContractError,
    MTFOrchestratorStateV1,
    MTFResearchPlanV1,
    MTFStage,
    state_to_json,
)


BRIDGE_SCHEMA = "event_long_mtf_execution_bridge_receipt_v1"
BRIDGE_NAME = "event_long_mtf_to_next_open_execution_v1"
BRIDGE_STATUS = "RESEARCH_ONLY_FROZEN_EXECUTION_CONTRACT"
PENDING_OUTBOX_DELIVERY_REQUIREMENT = (
    "the persisted adapter must freeze source advancement while an MTF plan is "
    "pending, persist the deterministic bridge result, and only then atomically "
    "acknowledge that exact MTF outbox plan"
)


class EventLongMTFBridgeError(ValueError):
    """MTF evidence cannot be bridged without weakening its contract."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EventLongMTFBridgeError(f"bridge evidence is not canonical JSON: {exc}") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_hex(value: object, length: int) -> bool:
    text = str(value or "")
    return len(text) == length and all(char in "0123456789abcdef" for char in text)


def _is_exact_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


def _receipt_evidence_payload(receipt: "MTFExecutionBridgeReceiptV1") -> dict[str, Any]:
    """Canonical evidence whose SHA256 is passed to the execution contract."""
    return {
        "schema": receipt.schema,
        "bridge": receipt.bridge,
        "status": receipt.status,
        "mtf_strategy": receipt.mtf_strategy,
        "mtf_plan_id": receipt.mtf_plan_id,
        "mtf_idempotency_key": receipt.mtf_idempotency_key,
        "event_id": receipt.event_id,
        "level_id": receipt.level_id,
        "level_snapshot_id": receipt.level_snapshot_id,
        "symbol": receipt.symbol,
        "side": receipt.side,
        "side_identity": receipt.side_identity,
        "signal_open_ts_ms": receipt.signal_open_ts_ms,
        "signal_known_at_ms": receipt.signal_known_at_ms,
        "valid_from_m5_open_ts_ms": receipt.valid_from_m5_open_ts_ms,
        "valid_until_m5_open_ts_ms": receipt.valid_until_m5_open_ts_ms,
        "entry_reference": receipt.entry_reference,
        "frozen_stop": receipt.frozen_stop,
        "mtf_state_payload_sha256": receipt.mtf_state_payload_sha256,
        "mtf_plan_payload_sha256": receipt.mtf_plan_payload_sha256,
        "event_payload_sha256": receipt.event_payload_sha256,
        "level_snapshot_sha256": receipt.level_snapshot_sha256,
        "level_frozen_payload_sha256": receipt.level_frozen_payload_sha256,
        "raw_m5_source_sha256": receipt.raw_m5_source_sha256,
        "raw_m5_source_start_open_ts_ms": receipt.raw_m5_source_start_open_ts_ms,
        "raw_m5_source_count": receipt.raw_m5_source_count,
        "provider_identity": receipt.provider_identity,
        "provider_fingerprint": receipt.provider_fingerprint,
        "strategy_config_sha256": receipt.strategy_config_sha256,
        "aggregation_config_fingerprints": [
            list(item) for item in receipt.aggregation_config_fingerprints
        ],
        "h1_source_sha256": receipt.h1_source_sha256,
        "h1_output_sha256": receipt.h1_output_sha256,
        "h1_aggregation_config_sha256": receipt.h1_aggregation_config_sha256,
        "m15_source_sha256": receipt.m15_source_sha256,
        "m15_output_sha256": receipt.m15_output_sha256,
        "m15_aggregation_config_sha256": receipt.m15_aggregation_config_sha256,
        "level_source_mode": receipt.level_source_mode,
        "level_source_sha256": receipt.level_source_sha256,
        "level_output_sha256": receipt.level_output_sha256,
        "level_aggregation_config_sha256": receipt.level_aggregation_config_sha256,
        "m5_watermark_close_ms": receipt.m5_watermark_close_ms,
        "m15_watermark_close_ms": receipt.m15_watermark_close_ms,
        "h1_watermark_close_ms": receipt.h1_watermark_close_ms,
        "research_only": receipt.research_only,
        "broker_calls": receipt.broker_calls,
        "performance_claims": receipt.performance_claims,
        "executable": receipt.executable,
    }


@dataclass(frozen=True)
class MTFExecutionBridgeReceiptV1:
    """Authenticated evidence for one research-only MTF-to-execution conversion."""

    receipt_id: str
    source_fingerprint: str
    mtf_plan_id: str
    mtf_idempotency_key: str
    event_id: str
    level_id: str
    level_snapshot_id: str
    symbol: str
    signal_open_ts_ms: int
    signal_known_at_ms: int
    valid_from_m5_open_ts_ms: int
    valid_until_m5_open_ts_ms: int
    entry_reference: float
    frozen_stop: float
    mtf_state_payload_sha256: str
    mtf_plan_payload_sha256: str
    event_payload_sha256: str
    level_snapshot_sha256: str
    level_frozen_payload_sha256: str
    raw_m5_source_sha256: str
    raw_m5_source_start_open_ts_ms: int
    raw_m5_source_count: int
    provider_identity: str
    provider_fingerprint: str
    strategy_config_sha256: str
    aggregation_config_fingerprints: Tuple[Tuple[str, str], ...]
    h1_source_sha256: str
    h1_output_sha256: str
    h1_aggregation_config_sha256: str
    m15_source_sha256: str
    m15_output_sha256: str
    m15_aggregation_config_sha256: str
    level_source_mode: str
    level_source_sha256: str
    level_output_sha256: str
    level_aggregation_config_sha256: str
    m5_watermark_close_ms: int
    m15_watermark_close_ms: int
    h1_watermark_close_ms: int
    schema: str = BRIDGE_SCHEMA
    bridge: str = BRIDGE_NAME
    status: str = BRIDGE_STATUS
    mtf_strategy: str = STRATEGY_NAME
    side: str = "long"
    side_identity: str = SIDE_IDENTITY
    research_only: bool = True
    broker_calls: bool = False
    performance_claims: bool = False
    executable: bool = False

    def __post_init__(self) -> None:
        if (self.schema, self.bridge, self.status, self.mtf_strategy) != (
            BRIDGE_SCHEMA,
            BRIDGE_NAME,
            BRIDGE_STATUS,
            STRATEGY_NAME,
        ):
            raise EventLongMTFBridgeError("bridge schema/name/status/strategy mismatch")
        if self.side != "long" or self.side_identity != SIDE_IDENTITY:
            raise EventLongMTFBridgeError("bridge is physically long-only")
        if not self.research_only or self.broker_calls or self.performance_claims or self.executable:
            raise EventLongMTFBridgeError("bridge must remain non-executable research infrastructure")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise EventLongMTFBridgeError("bridge symbol must be canonical uppercase")
        if not self.provider_identity or self.provider_identity != self.provider_identity.strip():
            raise EventLongMTFBridgeError("provider identity must be a canonical non-empty string")
        if not all(
            _is_hex(value, 32)
            for value in (
                self.receipt_id,
                self.mtf_plan_id,
                self.mtf_idempotency_key,
                self.event_id,
                self.level_id,
                self.level_snapshot_id,
            )
        ):
            raise EventLongMTFBridgeError("bridge identities must be lowercase 32-character hex")
        if self.mtf_plan_id != self.mtf_idempotency_key:
            raise EventLongMTFBridgeError("MTF plan/idempotency identities diverged")
        hashes = (
            self.source_fingerprint,
            self.mtf_state_payload_sha256,
            self.mtf_plan_payload_sha256,
            self.event_payload_sha256,
            self.level_snapshot_sha256,
            self.level_frozen_payload_sha256,
            self.raw_m5_source_sha256,
            self.provider_fingerprint,
            self.strategy_config_sha256,
            self.h1_source_sha256,
            self.h1_output_sha256,
            self.h1_aggregation_config_sha256,
            self.m15_source_sha256,
            self.m15_output_sha256,
            self.m15_aggregation_config_sha256,
            self.level_source_sha256,
            self.level_output_sha256,
            self.level_aggregation_config_sha256,
        )
        if not all(_is_hex(value, 64) for value in hashes):
            raise EventLongMTFBridgeError("bridge evidence hashes must be lowercase SHA256")
        expected_timeframes = ("M15", "H1", "H4")
        if (
            tuple(item[0] for item in self.aggregation_config_fingerprints)
            != expected_timeframes
            or not all(_is_hex(item[1], 64) for item in self.aggregation_config_fingerprints)
        ):
            raise EventLongMTFBridgeError("aggregation fingerprints must bind canonical M15/H1/H4")
        for name in (
            "signal_open_ts_ms",
            "signal_known_at_ms",
            "valid_from_m5_open_ts_ms",
            "valid_until_m5_open_ts_ms",
            "raw_m5_source_start_open_ts_ms",
            "raw_m5_source_count",
            "m5_watermark_close_ms",
            "m15_watermark_close_ms",
            "h1_watermark_close_ms",
        ):
            if not _is_exact_int(getattr(self, name)):
                raise EventLongMTFBridgeError(f"{name} must be an exact integer")
        if self.signal_open_ts_ms < 0 or self.signal_open_ts_ms % M15:
            raise EventLongMTFBridgeError("signal open must be an exact M15 candle-open")
        if (
            self.signal_known_at_ms != self.signal_open_ts_ms + M15
            or self.valid_from_m5_open_ts_ms != self.signal_known_at_ms
            or self.valid_until_m5_open_ts_ms != self.valid_from_m5_open_ts_ms + M5
            or self.valid_from_m5_open_ts_ms % M5
        ):
            raise EventLongMTFBridgeError("bridge does not target the exact next M5 boundary")
        if (
            self.m5_watermark_close_ms != self.valid_from_m5_open_ts_ms
            or self.m15_watermark_close_ms != self.valid_from_m5_open_ts_ms
            or self.h1_watermark_close_ms
            != self.valid_from_m5_open_ts_ms - self.valid_from_m5_open_ts_ms % (4 * M15)
        ):
            raise EventLongMTFBridgeError("outer state was not frozen at the decision boundary")
        if self.raw_m5_source_count <= 0 or self.raw_m5_source_start_open_ts_ms < 0:
            raise EventLongMTFBridgeError("raw M5 source span is invalid")
        if (
            self.raw_m5_source_start_open_ts_ms
            + self.raw_m5_source_count * M5
            != self.m5_watermark_close_ms
        ):
            raise EventLongMTFBridgeError("raw M5 source count/span does not reach the boundary")
        if not (_finite_positive(self.entry_reference) and _finite_positive(self.frozen_stop)):
            raise EventLongMTFBridgeError("entry/stop must be finite positive numbers")
        if self.frozen_stop >= self.entry_reference:
            raise EventLongMTFBridgeError("long frozen stop must remain below entry reference")
        if self.level_source_mode != "closed_bar_aggregation_v1":
            raise EventLongMTFBridgeError("bridge requires M5-derived closed-bar level evidence")
        expected_source = _sha256(_receipt_evidence_payload(self))
        expected_receipt_id = _sha256({
            "schema": self.schema,
            "bridge": self.bridge,
            "source_fingerprint": expected_source,
        })[:32]
        if self.source_fingerprint != expected_source or self.receipt_id != expected_receipt_id:
            raise EventLongMTFBridgeError("bridge receipt/source fingerprint does not bind evidence")


@dataclass(frozen=True)
class MTFExecutionBridgeResultV1:
    """One receipt plus the distinct immutable execution-plan identity."""

    receipt: MTFExecutionBridgeReceiptV1
    frozen_plan: FrozenLongPlanV1
    research_only: bool = True
    broker_calls: bool = False
    performance_claims: bool = False

    def __post_init__(self) -> None:
        if not self.research_only or self.broker_calls or self.performance_claims:
            raise EventLongMTFBridgeError("bridge result must remain research-only")
        if self.frozen_plan.source_fingerprint != self.receipt.source_fingerprint:
            raise EventLongMTFBridgeError("execution plan is not bound to the bridge receipt")
        if self.frozen_plan.plan_id == self.receipt.mtf_plan_id:
            raise EventLongMTFBridgeError("MTF and execution plan identities must remain distinct")
        if (
            self.frozen_plan.event_id != self.receipt.event_id
            or self.frozen_plan.level_id != self.receipt.level_id
            or self.frozen_plan.strategy != self.receipt.mtf_strategy
            or self.frozen_plan.symbol != self.receipt.symbol
            or self.frozen_plan.signal_open_ts != self.receipt.signal_open_ts_ms
            or self.frozen_plan.signal_known_at_ts != self.receipt.signal_known_at_ms
            or self.frozen_plan.valid_from_ts != self.receipt.valid_from_m5_open_ts_ms
            or self.frozen_plan.entry_reference != self.receipt.entry_reference
            or self.frozen_plan.frozen_stop != self.receipt.frozen_stop
        ):
            raise EventLongMTFBridgeError("execution plan fields diverged from bridge evidence")
        if not self.frozen_plan.research_only or self.frozen_plan.broker_calls:
            raise EventLongMTFBridgeError("execution plan unexpectedly became live-capable")


def _make_receipt(values: Mapping[str, Any]) -> MTFExecutionBridgeReceiptV1:
    """Construct the self-authenticating receipt without a circular hash."""
    probe = MTFExecutionBridgeReceiptV1.__new__(MTFExecutionBridgeReceiptV1)
    for field_name, value in values.items():
        object.__setattr__(probe, field_name, value)
    defaults = {
        "schema": BRIDGE_SCHEMA,
        "bridge": BRIDGE_NAME,
        "status": BRIDGE_STATUS,
        "mtf_strategy": STRATEGY_NAME,
        "side": "long",
        "side_identity": SIDE_IDENTITY,
        "research_only": True,
        "broker_calls": False,
        "performance_claims": False,
        "executable": False,
    }
    for field_name, value in defaults.items():
        object.__setattr__(probe, field_name, value)
    source_fingerprint = _sha256(_receipt_evidence_payload(probe))
    receipt_id = _sha256({
        "schema": BRIDGE_SCHEMA,
        "bridge": BRIDGE_NAME,
        "source_fingerprint": source_fingerprint,
    })[:32]
    return MTFExecutionBridgeReceiptV1(
        receipt_id=receipt_id,
        source_fingerprint=source_fingerprint,
        **values,
    )


def bridge_mtf_research_plan_v1(
    plan: MTFResearchPlanV1,
    state: MTFOrchestratorStateV1,
) -> MTFExecutionBridgeResultV1:
    """Freeze an authenticated outbox plan for research execution only.

    This function does not acknowledge or mutate ``state``.  The persisted
    adapter must refuse further M5 advancement while the plan is pending,
    persist this deterministic bridge result, and only then atomically
    acknowledge the exact outbox item.  Durable acknowledgement cannot be
    inferred from an in-memory conversion.
    """
    if not isinstance(plan, MTFResearchPlanV1) or not isinstance(state, MTFOrchestratorStateV1):
        raise EventLongMTFBridgeError("bridge requires exact MTF v1 plan/state types")
    try:
        # Re-run nested validators as defense against objects constructed via
        # ``__new__`` or deserializers that bypass dataclass post-init hooks.
        plan.__post_init__()
        state_envelope = json.loads(state_to_json(state))
    except (MTFContractError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EventLongMTFBridgeError(f"invalid MTF plan/state: {exc}") from exc

    matches = tuple(item for item in state.plan_outbox if item.plan_id == plan.plan_id)
    if len(matches) != 1 or matches[0] != plan:
        raise EventLongMTFBridgeError("exact MTF plan is not uniquely present in the atomic outbox")
    if plan.plan_id in state.acknowledged_plan_ids:
        raise EventLongMTFBridgeError("MTF plan was already acknowledged")
    active = state.active
    if (
        active is None
        or active.stage != MTFStage.PLAN_EMITTED
        or active.emitted_plan_id != plan.plan_id
        or active.last_m15_close_ms != plan.known_at_ms
        or active.terminal_reason != "one_plan_to_atomic_outbox"
    ):
        raise EventLongMTFBridgeError("outer active state does not match the emitted outbox plan")
    event = active.event
    level = event.level_snapshot
    try:
        event.__post_init__()
        level.__post_init__()
    except (MTFContractError, TypeError, ValueError) as exc:
        raise EventLongMTFBridgeError(f"invalid event/level evidence: {exc}") from exc

    if (
        plan.side != "long"
        or state.side_identity != SIDE_IDENTITY
        or event.side != "long"
        or plan.symbol != state.symbol
        or event.symbol != state.symbol
        or level.symbol != state.symbol
    ):
        raise EventLongMTFBridgeError("plan/state/event/level are not the same long-only symbol")
    if (
        plan.event_id != event.event_id
        or plan.level_id != level.level_id
        or event.level_snapshot.level_id != level.level_id
        or plan.config_sha256 != state.config_sha256
        or event.config_sha256 != state.config_sha256
        or event.provider_fingerprint != state.provider_fingerprint
        or level.provider_fingerprint != state.provider_fingerprint
    ):
        raise EventLongMTFBridgeError("plan/event/level/source/config identities diverged")
    if (
        plan.known_at_ms != plan.bos_bar_open_ts_ms + M15
        or plan.valid_from_m5_open_ts_ms != plan.known_at_ms
        or plan.valid_until_m5_open_ts_ms != plan.known_at_ms + M5
        or state.m5_watermark_close_ms != plan.known_at_ms
        or state.m15_watermark_close_ms != plan.known_at_ms
    ):
        raise EventLongMTFBridgeError("conversion missed the exact closed-M15 / next-M5 boundary")
    if (
        plan.stop_price >= plan.entry_reference
        or not math.isclose(
            plan.risk_distance,
            plan.entry_reference - plan.stop_price,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        raise EventLongMTFBridgeError("MTF frozen long risk geometry is inconsistent")

    provenance = level.source_provenance
    if (
        provenance.mode != "closed_bar_aggregation_v1"
        or provenance.provider_fingerprint != state.provider_fingerprint
        or provenance.source_timeframe != "M5"
        or provenance.output_timeframe != level.timeframe
        or provenance.output_sha256 != level.source_bars_sha256
    ):
        raise EventLongMTFBridgeError("level lacks matching M5-to-HTF aggregation evidence")

    event_payload = asdict(event)
    level_payload = level_snapshot_to_dict(level)
    values = {
        "mtf_plan_id": plan.plan_id,
        "mtf_idempotency_key": plan.idempotency_key,
        "event_id": event.event_id,
        "level_id": level.level_id,
        "level_snapshot_id": level.snapshot_id,
        "symbol": plan.symbol,
        "signal_open_ts_ms": plan.bos_bar_open_ts_ms,
        "signal_known_at_ms": plan.known_at_ms,
        "valid_from_m5_open_ts_ms": plan.valid_from_m5_open_ts_ms,
        "valid_until_m5_open_ts_ms": plan.valid_until_m5_open_ts_ms,
        "entry_reference": plan.entry_reference,
        "frozen_stop": plan.stop_price,
        "mtf_state_payload_sha256": str(state_envelope["payload_sha256"]),
        "mtf_plan_payload_sha256": _sha256(asdict(plan)),
        "event_payload_sha256": _sha256(event_payload),
        "level_snapshot_sha256": _sha256(level_payload),
        "level_frozen_payload_sha256": level.payload_sha256,
        "raw_m5_source_sha256": state.source_sha256,
        "raw_m5_source_start_open_ts_ms": state.source_start_open_ts_ms,
        "raw_m5_source_count": state.source_count,
        "provider_identity": state.provider_identity,
        "provider_fingerprint": state.provider_fingerprint,
        "strategy_config_sha256": state.config_sha256,
        "aggregation_config_fingerprints": state.aggregation_config_fingerprints,
        "h1_source_sha256": event.h1_source_sha256,
        "h1_output_sha256": event.h1_output_sha256,
        "h1_aggregation_config_sha256": event.h1_aggregation_config_sha256,
        "m15_source_sha256": plan.m15_source_sha256,
        "m15_output_sha256": plan.m15_output_sha256,
        "m15_aggregation_config_sha256": plan.m15_aggregation_config_sha256,
        "level_source_mode": provenance.mode,
        "level_source_sha256": provenance.source_sha256,
        "level_output_sha256": provenance.output_sha256,
        "level_aggregation_config_sha256": provenance.aggregation_config_sha256,
        "m5_watermark_close_ms": state.m5_watermark_close_ms,
        "m15_watermark_close_ms": state.m15_watermark_close_ms,
        "h1_watermark_close_ms": state.h1_watermark_close_ms,
    }
    receipt = _make_receipt(values)
    frozen = make_frozen_long_plan_v1(
        event_id=event.event_id,
        level_id=level.level_id,
        strategy=STRATEGY_NAME,
        symbol=plan.symbol,
        signal_open_ts=plan.bos_bar_open_ts_ms,
        entry_reference=plan.entry_reference,
        frozen_stop=plan.stop_price,
        source_fingerprint=receipt.source_fingerprint,
    )
    return MTFExecutionBridgeResultV1(receipt=receipt, frozen_plan=frozen)


__all__ = [
    "BRIDGE_NAME",
    "BRIDGE_SCHEMA",
    "BRIDGE_STATUS",
    "PENDING_OUTBOX_DELIVERY_REQUIREMENT",
    "EventLongMTFBridgeError",
    "MTFExecutionBridgeReceiptV1",
    "MTFExecutionBridgeResultV1",
    "bridge_mtf_research_plan_v1",
]
