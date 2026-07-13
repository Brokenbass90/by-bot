"""Atomic fail-closed state for the research-only long event sleeve."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from bot.level_snapshot_v1 import (
    LevelSnapshotError,
    level_snapshot_from_dict,
    level_snapshot_to_dict,
)
from strategies.event_expansion_retest_long_v1 import (
    EventExpansionRetestLongV1Research,
    ExpansionRetestLongConfig,
    LongEventStage,
    LongEventState,
    LongExpansionEvent,
    LongSleeveState,
    SIDE_IDENTITY,
    STRATEGY_NAME,
)


STATE_SCHEMA = "event_expansion_retest_long_state"
STATE_VERSION = 1


class LongStateValidationError(RuntimeError):
    """Persisted state is unsafe; callers must not silently reset it."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LongStateValidationError(f"state is not canonical JSON: {exc}") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LongStateValidationError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise LongStateValidationError(f"{name} keys mismatch")


def _ledger(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise LongStateValidationError(f"{name} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise LongStateValidationError(f"{name} contains duplicates")
    return tuple(value)


def _event_to_obj(event: LongExpansionEvent) -> dict[str, Any]:
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
        "initial_atr": event.initial_atr,
        "signal_interval_ms": event.signal_interval_ms,
        "config_sha256": event.config_sha256,
        "level_snapshot": level_snapshot_to_dict(event.level_snapshot),
        "expires_ts": event.expires_ts,
    }


def _event_from_obj(raw: object, *, symbol: str) -> LongExpansionEvent:
    obj = _mapping(raw, "event")
    expected = {
        "event_id", "strategy", "symbol", "side", "expansion_ts",
        "expansion_open", "expansion_high", "expansion_low", "expansion_close",
        "expansion_volume", "initial_atr", "signal_interval_ms", "config_sha256", "level_snapshot",
        "expires_ts",
    }
    _keys(obj, expected, "event")
    if obj["strategy"] != STRATEGY_NAME or obj["side"] != "long" or obj["symbol"] != symbol:
        raise LongStateValidationError("event violates physical long-only identity")
    try:
        return LongExpansionEvent(
            event_id=str(obj["event_id"]), strategy=str(obj["strategy"]),
            symbol=str(obj["symbol"]), side=str(obj["side"]),
            expansion_ts=int(obj["expansion_ts"]),
            expansion_open=float(obj["expansion_open"]),
            expansion_high=float(obj["expansion_high"]),
            expansion_low=float(obj["expansion_low"]),
            expansion_close=float(obj["expansion_close"]),
            expansion_volume=float(obj["expansion_volume"]),
            initial_atr=float(obj["initial_atr"]),
            signal_interval_ms=int(obj["signal_interval_ms"]),
            config_sha256=str(obj["config_sha256"]),
            level_snapshot=level_snapshot_from_dict(obj["level_snapshot"]),
            expires_ts=int(obj["expires_ts"]),
        )
    except (TypeError, ValueError, LevelSnapshotError) as exc:
        raise LongStateValidationError(f"invalid event: {exc}") from exc


def _state_to_obj(state: LongSleeveState) -> dict[str, Any]:
    active = state.active
    return {
        "active": None if active is None else {
            "event": _event_to_obj(active.event),
            "stage": active.stage.value,
            "last_processed_ts": active.last_processed_ts,
            "hold_count": active.hold_count,
            "first_retest_ts": active.first_retest_ts,
            "retest_low": active.retest_low,
            "structure_level": active.structure_level,
            "terminal_reason": active.terminal_reason,
        },
        "seen_event_ids": list(state.seen_event_ids),
        "planned_event_ids": list(state.planned_event_ids),
    }


def _state_from_obj(raw: object, *, symbol: str) -> LongSleeveState:
    obj = _mapping(raw, f"states.{symbol}")
    _keys(obj, {"active", "seen_event_ids", "planned_event_ids"}, f"states.{symbol}")
    seen = _ledger(obj["seen_event_ids"], "seen_event_ids")
    planned = _ledger(obj["planned_event_ids"], "planned_event_ids")
    active_raw = obj["active"]
    active: Optional[LongEventState] = None
    if active_raw is not None:
        item = _mapping(active_raw, "active")
        _keys(
            item,
            {"event", "stage", "last_processed_ts", "hold_count",
             "first_retest_ts", "retest_low", "structure_level", "terminal_reason"},
            "active",
        )
        try:
            active = LongEventState(
                event=_event_from_obj(item["event"], symbol=symbol),
                stage=LongEventStage(str(item["stage"])),
                last_processed_ts=int(item["last_processed_ts"]),
                hold_count=int(item["hold_count"]),
                first_retest_ts=(None if item["first_retest_ts"] is None else int(item["first_retest_ts"])),
                retest_low=None if item["retest_low"] is None else float(item["retest_low"]),
                structure_level=(None if item["structure_level"] is None else float(item["structure_level"])),
                terminal_reason=str(item["terminal_reason"]),
            )
        except (TypeError, ValueError) as exc:
            raise LongStateValidationError(f"invalid active state: {exc}") from exc
        if (
            active.last_processed_ts < active.event.expansion_ts
            or active.last_processed_ts % active.event.signal_interval_ms != 0
            or active.hold_count < 0
        ):
            raise LongStateValidationError("active state timeline/counter is invalid")
        retest_stages = {
            LongEventStage.FIRST_RETEST,
            LongEventStage.HIGHER_LOW_CONFIRMED,
            LongEventStage.PLAN_EMITTED,
        }
        if active.stage in retest_stages and (
            active.first_retest_ts is None
            or active.retest_low is None
            or active.structure_level is None
            or active.first_retest_ts <= active.event.expansion_ts
            or active.first_retest_ts % active.event.signal_interval_ms != 0
            or not math.isfinite(active.retest_low)
            or active.retest_low <= 0
            or not math.isfinite(active.structure_level)
            or active.structure_level <= 0
        ):
            raise LongStateValidationError("first-retest evidence is incomplete")
        if active.event.event_id not in seen:
            raise LongStateValidationError("active event is missing from seen_event_ids")
        if active.stage == LongEventStage.PLAN_EMITTED and active.event.event_id not in planned:
            raise LongStateValidationError("emitted plan is missing from planned_event_ids")
    return LongSleeveState(active, seen, planned)


class LongEventStateStore:
    def __init__(self, path: Path | str, *, source_fingerprint: str):
        self.path = Path(path)
        self.source_fingerprint = str(source_fingerprint or "").lower()
        if not _is_sha(self.source_fingerprint):
            raise ValueError("source_fingerprint must be lowercase SHA256")

    def _reject_symlink(self) -> None:
        if self.path.is_symlink():
            raise LongStateValidationError("refusing long-event state symlink")

    def load(self) -> dict[str, LongSleeveState]:
        self._reject_symlink()
        if not self.path.exists():
            return {}
        try:
            env = _mapping(json.loads(self.path.read_text(encoding="utf-8")), "envelope")
        except (OSError, json.JSONDecodeError) as exc:
            raise LongStateValidationError(f"state is unreadable: {exc}") from exc
        _keys(
            env,
            {"schema", "version", "strategy", "side_identity", "source_fingerprint",
             "saved_at_utc", "payload", "payload_sha256"},
            "envelope",
        )
        if env["schema"] != STATE_SCHEMA or env["version"] != STATE_VERSION:
            raise LongStateValidationError("state schema/version mismatch")
        if env["strategy"] != STRATEGY_NAME or env["side_identity"] != SIDE_IDENTITY:
            raise LongStateValidationError("state strategy/side identity mismatch")
        if env["source_fingerprint"] != self.source_fingerprint:
            raise LongStateValidationError("state source fingerprint mismatch")
        payload = _mapping(env["payload"], "payload")
        if env["payload_sha256"] != _sha(payload):
            raise LongStateValidationError("state payload checksum mismatch")
        _keys(payload, {"states"}, "payload")
        raw_states = _mapping(payload["states"], "payload.states")
        result: dict[str, LongSleeveState] = {}
        for raw_symbol, raw_state in raw_states.items():
            symbol = str(raw_symbol)
            if not symbol or symbol != symbol.upper():
                raise LongStateValidationError("state symbol key is not canonical")
            result[symbol] = _state_from_obj(raw_state, symbol=symbol)
        return result

    def save(self, states: Mapping[str, LongSleeveState]) -> None:
        self._reject_symlink()
        serialized: dict[str, Any] = {}
        for raw_symbol in sorted(states):
            symbol = str(raw_symbol)
            if not symbol or symbol != symbol.upper():
                raise LongStateValidationError("state symbol key is not canonical")
            obj = _state_to_obj(states[raw_symbol])
            _state_from_obj(obj, symbol=symbol)  # validate before replace
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
            "payload_sha256": _sha(payload),
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
        finally:
            if tmp.exists():
                tmp.unlink()


class PersistedEventExpansionRetestLongV1Research(EventExpansionRetestLongV1Research):
    PERSISTED_EVENT_STATE = True

    def __init__(
        self, *, state_path: Path | str, source_fingerprint: str,
        cfg: Optional[ExpansionRetestLongConfig] = None,
    ):
        super().__init__(cfg=cfg)
        self.state_store = LongEventStateStore(
            state_path, source_fingerprint=source_fingerprint
        )
        self._states = self.state_store.load()

    def process_closed_rows(self, symbol: str, rows: Sequence[Sequence[Any]], level_snapshots):
        canonical = str(symbol).upper()
        before = self._states.get(canonical)
        step = super().process_closed_rows(canonical, rows, level_snapshots)
        if self._states.get(canonical) != before:
            self.state_store.save(self._states)
        return step


__all__ = [
    "LongEventStateStore", "LongStateValidationError",
    "PersistedEventExpansionRetestLongV1Research", "STATE_SCHEMA", "STATE_VERSION",
]
