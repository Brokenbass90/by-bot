"""Fail-closed persisted FSM state for pump-exhaustion research.

This module does not place orders and is not wired into a live router.  It
persists the event state required by ``pump_exhaustion_unwind_short_v1`` so a
research/shadow process cannot forget an already-seen event after a restart.

The on-disk envelope has three independent identity checks:

* fixed schema/version;
* physical strategy/side identity (the sleeve is short-only);
* caller-supplied source fingerprint plus a canonical payload checksum.

Any malformed or mismatching state raises ``StateValidationError``.  There is
no "start empty on error" fallback because that could emit the same event a
second time.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from strategies.pump_exhaustion_unwind_short_v1 import (
    EventStage,
    FrozenHighLevels,
    PumpEventState,
    PumpExpansionEvent,
    PumpExhaustionUnwindShortV1Strategy,
    PumpUnwindConfig,
    STRATEGY_NAME,
    SleeveState,
)


STATE_SCHEMA = "pump_exhaustion_unwind_short_state"
STATE_VERSION = 1
SIDE_IDENTITY = "short_only"


class StateValidationError(RuntimeError):
    """Persisted state is unsafe to consume and must not be reset silently."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    try:
        return hashlib.sha256(_canonical_json(value)).hexdigest()
    except (TypeError, ValueError) as exc:
        raise StateValidationError(f"state payload is not canonical JSON: {exc}") from exc


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _expect_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StateValidationError(f"{name} must be an object")
    return value


def _expect_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise StateValidationError(
            f"{name} keys mismatch missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def _levels_to_obj(levels: FrozenHighLevels) -> dict[str, Any]:
    return {
        "horizontal_high": levels.horizontal_high,
        "sloped_high": levels.sloped_high,
        "liquidity_high": levels.liquidity_high,
        "anchor_level": levels.anchor_level,
        "anchor_source": levels.anchor_source,
        "crossed_sources": list(levels.crossed_sources),
    }


def _levels_from_obj(raw: object) -> FrozenHighLevels:
    obj = _expect_mapping(raw, "levels")
    _expect_keys(
        obj,
        {
            "horizontal_high",
            "sloped_high",
            "liquidity_high",
            "anchor_level",
            "anchor_source",
            "crossed_sources",
        },
        "levels",
    )
    crossed = obj["crossed_sources"]
    if not isinstance(crossed, list) or not crossed or not all(
        isinstance(item, str) and item for item in crossed
    ):
        raise StateValidationError("levels.crossed_sources must be non-empty strings")
    if len(set(crossed)) != len(crossed):
        raise StateValidationError("levels.crossed_sources contains duplicates")
    try:
        return FrozenHighLevels(
            horizontal_high=(
                None if obj["horizontal_high"] is None else float(obj["horizontal_high"])
            ),
            sloped_high=None if obj["sloped_high"] is None else float(obj["sloped_high"]),
            liquidity_high=float(obj["liquidity_high"]),
            anchor_level=float(obj["anchor_level"]),
            anchor_source=str(obj["anchor_source"]),
            crossed_sources=tuple(crossed),
        )
    except (TypeError, ValueError) as exc:
        raise StateValidationError(f"invalid frozen levels: {exc}") from exc


def _event_to_obj(event: PumpExpansionEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "strategy": event.strategy,
        "symbol": event.symbol,
        "side": event.side,
        "expansion_ts": event.expansion_ts,
        "expansion_open": event.expansion_open,
        "expansion_high": event.expansion_high,
        "expansion_low": event.expansion_low,
        "expansion_close": event.expansion_close,
        "expansion_volume": event.expansion_volume,
        "base_price": event.base_price,
        "initial_atr": event.initial_atr,
        "levels": _levels_to_obj(event.levels),
        "expires_ts": event.expires_ts,
    }


def _event_from_obj(raw: object, *, map_symbol: str) -> PumpExpansionEvent:
    obj = _expect_mapping(raw, "event")
    expected = {
        "event_id",
        "strategy",
        "symbol",
        "side",
        "expansion_ts",
        "expansion_open",
        "expansion_high",
        "expansion_low",
        "expansion_close",
        "expansion_volume",
        "base_price",
        "initial_atr",
        "levels",
        "expires_ts",
    }
    _expect_keys(obj, expected, "event")
    if obj["strategy"] != STRATEGY_NAME or obj["side"] != "short":
        raise StateValidationError("event violates short-only strategy identity")
    if str(obj["symbol"]) != map_symbol:
        raise StateValidationError("event symbol does not match state map key")
    try:
        return PumpExpansionEvent(
            event_id=str(obj["event_id"]),
            strategy=str(obj["strategy"]),
            symbol=str(obj["symbol"]).upper(),
            side=str(obj["side"]),
            expansion_ts=int(obj["expansion_ts"]),
            expansion_open=float(obj["expansion_open"]),
            expansion_high=float(obj["expansion_high"]),
            expansion_low=float(obj["expansion_low"]),
            expansion_close=float(obj["expansion_close"]),
            expansion_volume=float(obj["expansion_volume"]),
            base_price=float(obj["base_price"]),
            initial_atr=float(obj["initial_atr"]),
            levels=_levels_from_obj(obj["levels"]),
            expires_ts=int(obj["expires_ts"]),
        )
    except (TypeError, ValueError) as exc:
        raise StateValidationError(f"invalid event: {exc}") from exc


def _active_to_obj(active: PumpEventState) -> dict[str, Any]:
    return {
        "event": _event_to_obj(active.event),
        "stage": active.stage.value,
        "last_processed_ts": active.last_processed_ts,
        "peak_price": active.peak_price,
        "exhaustion_ts": active.exhaustion_ts,
        "choch_ts": active.choch_ts,
        "choch_level": active.choch_level,
        "terminal_reason": active.terminal_reason,
    }


def _active_from_obj(raw: object, *, map_symbol: str) -> PumpEventState:
    obj = _expect_mapping(raw, "active")
    _expect_keys(
        obj,
        {
            "event",
            "stage",
            "last_processed_ts",
            "peak_price",
            "exhaustion_ts",
            "choch_ts",
            "choch_level",
            "terminal_reason",
        },
        "active",
    )
    try:
        active = PumpEventState(
            event=_event_from_obj(obj["event"], map_symbol=map_symbol),
            stage=EventStage(str(obj["stage"])),
            last_processed_ts=int(obj["last_processed_ts"]),
            peak_price=float(obj["peak_price"]),
            exhaustion_ts=None if obj["exhaustion_ts"] is None else int(obj["exhaustion_ts"]),
            choch_ts=None if obj["choch_ts"] is None else int(obj["choch_ts"]),
            choch_level=None if obj["choch_level"] is None else float(obj["choch_level"]),
            terminal_reason=str(obj["terminal_reason"]),
        )
    except (TypeError, ValueError) as exc:
        raise StateValidationError(f"invalid active event state: {exc}") from exc
    if active.last_processed_ts < active.event.expansion_ts:
        raise StateValidationError("active.last_processed_ts predates expansion")
    if not math.isfinite(active.peak_price) or active.peak_price <= 0:
        raise StateValidationError("active.peak_price must be finite and positive")
    if active.stage in {
        EventStage.EXHAUSTED,
        EventStage.CHOCH_CONFIRMED,
        EventStage.PLAN_EMITTED,
    } and active.exhaustion_ts is None:
        raise StateValidationError("advanced state is missing exhaustion_ts")
    if active.exhaustion_ts is not None and active.exhaustion_ts < active.event.expansion_ts:
        raise StateValidationError("active.exhaustion_ts predates expansion")
    if active.stage in {EventStage.CHOCH_CONFIRMED, EventStage.PLAN_EMITTED} and (
        active.choch_ts is None or active.choch_level is None
    ):
        raise StateValidationError("CHoCH state is incomplete")
    if active.choch_ts is not None and (
        active.exhaustion_ts is None or active.choch_ts <= active.exhaustion_ts
    ):
        raise StateValidationError("active.choch_ts must follow exhaustion_ts")
    if active.choch_level is not None and (
        not math.isfinite(active.choch_level) or active.choch_level <= 0
    ):
        raise StateValidationError("active.choch_level must be finite and positive")
    return active


def _sleeve_to_obj(state: SleeveState) -> dict[str, Any]:
    return {
        "active": None if state.active is None else _active_to_obj(state.active),
        "seen_event_ids": list(state.seen_event_ids),
        "planned_event_ids": list(state.planned_event_ids),
    }


def _ledger(raw: object, name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise StateValidationError(f"{name} must be a list of non-empty strings")
    if len(raw) != len(set(raw)):
        raise StateValidationError(f"{name} contains duplicates")
    return tuple(raw)


def _sleeve_from_obj(raw: object, *, symbol: str) -> SleeveState:
    obj = _expect_mapping(raw, f"states.{symbol}")
    _expect_keys(obj, {"active", "seen_event_ids", "planned_event_ids"}, f"states.{symbol}")
    seen = _ledger(obj["seen_event_ids"], "seen_event_ids")
    planned = _ledger(obj["planned_event_ids"], "planned_event_ids")
    # Both ledgers are independently bounded.  A legitimately old planned ID
    # may outlive the corresponding entry in the higher-churn seen ledger.
    active = None if obj["active"] is None else _active_from_obj(obj["active"], map_symbol=symbol)
    if active is not None and active.event.event_id not in seen:
        raise StateValidationError("active event is missing from seen_event_ids")
    if (
        active is not None
        and active.stage == EventStage.PLAN_EMITTED
        and active.event.event_id not in planned
    ):
        raise StateValidationError("emitted plan is missing from planned_event_ids")
    return SleeveState(active=active, seen_event_ids=seen, planned_event_ids=planned)


class PumpEventStateStore:
    """Atomic JSON store for all per-symbol sleeve states."""

    def __init__(self, path: Path | str, *, source_fingerprint: str):
        self.path = Path(path)
        self.source_fingerprint = str(source_fingerprint).lower()
        if not _is_sha256(self.source_fingerprint):
            raise ValueError("source_fingerprint must be a lowercase SHA256")

    def _reject_symlink(self) -> None:
        if self.path.is_symlink():
            raise StateValidationError("refusing pump state symlink")

    def load(self) -> dict[str, SleeveState]:
        self._reject_symlink()
        if not self.path.exists():
            return {}
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateValidationError(f"state JSON is unreadable: {exc}") from exc
        env = _expect_mapping(envelope, "state envelope")
        _expect_keys(
            env,
            {
                "schema",
                "version",
                "strategy",
                "side_identity",
                "source_fingerprint",
                "saved_at_utc",
                "payload",
                "payload_sha256",
            },
            "state envelope",
        )
        if env["schema"] != STATE_SCHEMA or env["version"] != STATE_VERSION:
            raise StateValidationError("state schema/version mismatch")
        if env["strategy"] != STRATEGY_NAME or env["side_identity"] != SIDE_IDENTITY:
            raise StateValidationError("state strategy/side identity mismatch")
        if env["source_fingerprint"] != self.source_fingerprint:
            raise StateValidationError("state source fingerprint mismatch")
        payload = _expect_mapping(env["payload"], "payload")
        if env["payload_sha256"] != _sha256_json(payload):
            raise StateValidationError("state payload checksum mismatch")
        _expect_keys(payload, {"states"}, "payload")
        raw_states = _expect_mapping(payload["states"], "payload.states")
        states: dict[str, SleeveState] = {}
        for raw_symbol, raw_state in raw_states.items():
            symbol = str(raw_symbol).upper()
            if symbol != raw_symbol or not symbol.endswith("USDT"):
                raise StateValidationError(f"invalid canonical symbol key: {raw_symbol!r}")
            states[symbol] = _sleeve_from_obj(raw_state, symbol=symbol)
        return states

    def save(self, states: Mapping[str, SleeveState]) -> None:
        self._reject_symlink()
        serialized: dict[str, Any] = {}
        for raw_symbol in sorted(states):
            symbol = str(raw_symbol).upper()
            if symbol != raw_symbol or not symbol.endswith("USDT"):
                raise StateValidationError(f"invalid canonical symbol key: {raw_symbol!r}")
            # Round-trip validation before replacing the last known-good file.
            obj = _sleeve_to_obj(states[raw_symbol])
            _sleeve_from_obj(obj, symbol=symbol)
            serialized[symbol] = obj
        payload = {"states": serialized}
        envelope = {
            "schema": STATE_SCHEMA,
            "version": STATE_VERSION,
            "strategy": STRATEGY_NAME,
            "side_identity": SIDE_IDENTITY,
            "source_fingerprint": self.source_fingerprint,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "payload_sha256": _sha256_json(payload),
        }
        data = json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("x", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            try:
                dir_fd = os.open(str(self.path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # The file replacement is already atomic; directory fsync is a
                # best-effort durability enhancement on supported filesystems.
                pass
        finally:
            if tmp.exists():
                tmp.unlink()


class PersistedPumpExhaustionUnwindShortV1Strategy(
    PumpExhaustionUnwindShortV1Strategy
):
    """Research adapter that saves FSM/ledgers whenever they change."""

    RESEARCH_ONLY = True
    LIVE_READY = False
    PERSISTED_EVENT_STATE = True
    SIDE_IDENTITY = SIDE_IDENTITY

    def __init__(
        self,
        *,
        state_path: Path | str,
        source_fingerprint: str,
        cfg: Optional[PumpUnwindConfig] = None,
    ):
        super().__init__(cfg=cfg)
        self.state_store = PumpEventStateStore(
            state_path,
            source_fingerprint=source_fingerprint,
        )
        # Fail closed: StateValidationError intentionally propagates.
        self._states = self.state_store.load()

    def process_closed_rows(
        self,
        symbol: str,
        rows: list[list[float]] | tuple[tuple[float, ...], ...] | Any,
    ):
        sym = str(symbol).upper()
        before = self._states.get(sym)
        plan = super().process_closed_rows(sym, rows)
        if self._states.get(sym) != before:
            self.state_store.save(self._states)
        return plan


__all__ = [
    "PersistedPumpExhaustionUnwindShortV1Strategy",
    "PumpEventStateStore",
    "SIDE_IDENTITY",
    "STATE_SCHEMA",
    "STATE_VERSION",
    "StateValidationError",
]
