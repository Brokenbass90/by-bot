"""Bounded, restartable public-data research station for cash-and-carry.

The station is deliberately an orchestration layer, not an exchange client and
not an executor.  It accepts a small adapter protocol that returns normalized
``PublicMarketSnapshotV2`` values and writes each symbol to its own frozen-v2
durable journal.  The only production adapter currently registered by the CLI
is Bybit public V5.  A future Bitget adapter must implement the same protocol
and receive its own preregistered source/engine contract; this module never
silently relabels Bitget data as Bybit data.

Safety properties:

* no API keys, environment reads, account/private endpoints, or order methods;
* default-disabled and explicit research/network/shadow opt-ins in the CLI;
* one process per run root, atomic checksummed lifecycle state, durable replay;
* separate append-only journal per symbol (the v2 engine is single-cycle);
* bounded time, observations, bytes, free-space floor, and failure budget;
* no deletion or rotation: reaching a bound stops fail-closed;
* scheduling wakes shortly after public funding timestamps so completed
  settlements can receive a contemporaneous public valuation proxy.

This is mechanics and evidence collection only.  It has no live authority and
does not make a performance claim.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Protocol

from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError, ShadowConfig
from bot.bybit_cashcarry_shadow_v2 import (
    DurableCashCarryJournalV2,
    DurableCollectorConfigV2,
    PublicMarketSnapshotV2,
)


STATION_SCHEMA_ID = "public_cashcarry_research_station_v1"
STATE_SCHEMA_ID = "public_cashcarry_station_state_v1"
LAUNCH_SCHEMA_ID = "public_cashcarry_station_launch_receipt_v1"
BYBIT_ADAPTER_ID = "bybit_public_v5_cashcarry_v1"
BYBIT_EXCHANGE_ID = "bybit"
BYBIT_SOURCE_ID = "bybit_public_v5"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CashCarryShadowError(f"{name} must be a positive integer")
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise CashCarryShadowError(f"{name} must be a positive integer") from exc
    if out <= 0 or float(value) != float(out):
        raise CashCarryShadowError(f"{name} must be a positive exact integer")
    return out


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CashCarryShadowError(f"{name} must be a non-negative integer")
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise CashCarryShadowError(f"{name} must be a non-negative integer") from exc
    if out < 0 or float(value) != float(out):
        raise CashCarryShadowError(f"{name} must be a non-negative exact integer")
    return out


class PublicCashCarryAdapter(Protocol):
    """Exchange adapter boundary used by the station.

    Adapters return a normalized snapshot and expose immutable identity.  They
    do not receive credentials or an account object.
    """

    adapter_id: str
    exchange_id: str
    source_id: str
    public_only: bool

    def fetch(self, symbol: str, *, timeout: float, book_limit: int) -> PublicMarketSnapshotV2:
        ...


@dataclass(frozen=True)
class FunctionPublicAdapter:
    """Small injectable adapter used by the CLI and deterministic tests."""

    adapter_id: str
    exchange_id: str
    source_id: str
    fetcher: Callable[..., PublicMarketSnapshotV2] = field(repr=False, compare=False)
    base_url: str = ""
    public_only: bool = True

    def __post_init__(self) -> None:
        if not self.adapter_id or not self.exchange_id or not self.source_id:
            raise CashCarryShadowError("adapter identity must be explicit")
        if self.public_only is not True:
            raise CashCarryShadowError("station adapter must be public-only")
        if not callable(self.fetcher):
            raise CashCarryShadowError("station adapter fetcher must be callable")

    def fetch(self, symbol: str, *, timeout: float, book_limit: int) -> PublicMarketSnapshotV2:
        kwargs: dict[str, Any] = {"timeout": timeout, "book_limit": book_limit}
        if self.base_url:
            kwargs["base"] = self.base_url
        snapshot = self.fetcher(symbol, **kwargs)
        if not isinstance(snapshot, PublicMarketSnapshotV2):
            raise CashCarryShadowError("adapter did not return PublicMarketSnapshotV2")
        return snapshot


@dataclass(frozen=True)
class StationConfigV1:
    spec_name: str
    spec_sha256: str
    adapter_id: str
    exchange_id: str
    source_id: str
    symbols: tuple[str, ...]
    poll_interval_seconds: int
    funding_capture_delay_seconds: int
    funding_capture_retry_seconds: int
    max_funding_valuation_lag_seconds: int
    transient_retry_seconds: int
    book_levels: int
    request_timeout_seconds: float
    max_runtime_seconds: int
    max_observations: int
    max_journal_bytes_per_symbol: int
    max_total_bytes: int
    max_append_reserve_bytes: int
    min_free_bytes: int
    max_consecutive_all_symbol_failure_cycles: int
    v2_spec_path: str
    v2_spec_sha256: str
    live_permission: str = "FORBIDDEN"

    def __post_init__(self) -> None:
        if self.live_permission != "FORBIDDEN":
            raise CashCarryShadowError("station live permission must remain forbidden")
        if self.adapter_id != BYBIT_ADAPTER_ID:
            raise CashCarryShadowError("only the preregistered Bybit public adapter is supported")
        if self.exchange_id != BYBIT_EXCHANGE_ID or self.source_id != BYBIT_SOURCE_ID:
            raise CashCarryShadowError("station exchange/source identity mismatch")
        symbols = tuple(str(item).strip().upper() for item in self.symbols)
        if not symbols or len(symbols) != len(set(symbols)):
            raise CashCarryShadowError("station symbols must be non-empty and unique")
        if any(not item.endswith("USDT") for item in symbols):
            raise CashCarryShadowError("station supports explicit USDT symbols only")
        object.__setattr__(self, "symbols", symbols)
        for name in (
            "poll_interval_seconds",
            "funding_capture_delay_seconds",
            "funding_capture_retry_seconds",
            "max_funding_valuation_lag_seconds",
            "transient_retry_seconds",
            "book_levels",
            "max_runtime_seconds",
            "max_observations",
            "max_journal_bytes_per_symbol",
            "max_total_bytes",
            "max_append_reserve_bytes",
            "min_free_bytes",
            "max_consecutive_all_symbol_failure_cycles",
        ):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        timeout = float(self.request_timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 60:
            raise CashCarryShadowError("request timeout must be in (0, 60]")
        object.__setattr__(self, "request_timeout_seconds", timeout)
        if not 2 <= self.book_levels <= 200:
            raise CashCarryShadowError("book_levels must be between 2 and 200")
        if self.funding_capture_delay_seconds >= self.max_funding_valuation_lag_seconds:
            raise CashCarryShadowError("funding capture delay must stay inside the valuation window")
        if self.max_funding_valuation_lag_seconds > 120:
            raise CashCarryShadowError("station valuation window cannot exceed frozen v2 120s")
        if self.funding_capture_retry_seconds >= self.max_funding_valuation_lag_seconds:
            raise CashCarryShadowError("funding retry must fit inside the valuation window")
        if self.max_total_bytes < self.max_journal_bytes_per_symbol:
            raise CashCarryShadowError("total byte cap cannot be below one symbol cap")
        if self.max_append_reserve_bytes >= self.max_journal_bytes_per_symbol:
            raise CashCarryShadowError("append reserve must be below the per-symbol cap")

    @property
    def config_sha256(self) -> str:
        return _sha256(dataclasses.asdict(self))


def load_station_config(path: Path, *, root: Path) -> tuple[Mapping[str, Any], StationConfigV1, ShadowConfig, DurableCollectorConfigV2]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != STATION_SCHEMA_ID:
        raise CashCarryShadowError("station spec schema mismatch")
    spec_sha = file_sha256(path)
    dependency = payload.get("frozen_v2_dependency") or {}
    v2_path = root / str(dependency.get("spec") or "")
    expected_v2_sha = str(dependency.get("spec_sha256") or "")
    if not v2_path.is_file() or file_sha256(v2_path) != expected_v2_sha:
        raise CashCarryShadowError("frozen v2 dependency is missing or hash-mismatched")
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    mechanics = v2.get("v1_mechanics")
    durable = v2.get("durable_collector")
    if not isinstance(mechanics, Mapping) or not isinstance(durable, Mapping):
        raise CashCarryShadowError("frozen v2 mechanics are incomplete")
    schedule = payload.get("schedule") or {}
    bounds = payload.get("bounds") or {}
    adapter = payload.get("adapter") or {}
    config = StationConfigV1(
        spec_name=str(payload.get("name") or ""),
        spec_sha256=spec_sha,
        adapter_id=str(adapter.get("adapter_id") or ""),
        exchange_id=str(adapter.get("exchange_id") or ""),
        source_id=str(adapter.get("source_id") or ""),
        symbols=tuple(payload.get("symbols") or ()),
        poll_interval_seconds=schedule["poll_interval_seconds"],
        funding_capture_delay_seconds=schedule["funding_capture_delay_seconds"],
        funding_capture_retry_seconds=schedule["funding_capture_retry_seconds"],
        max_funding_valuation_lag_seconds=schedule["max_funding_valuation_lag_seconds"],
        transient_retry_seconds=schedule["transient_retry_seconds"],
        book_levels=schedule["book_levels"],
        request_timeout_seconds=schedule["request_timeout_seconds"],
        max_runtime_seconds=bounds["max_runtime_seconds"],
        max_observations=bounds["max_observations"],
        max_journal_bytes_per_symbol=bounds["max_journal_bytes_per_symbol"],
        max_total_bytes=bounds["max_total_bytes"],
        max_append_reserve_bytes=bounds["max_append_reserve_bytes"],
        min_free_bytes=bounds["min_free_bytes"],
        max_consecutive_all_symbol_failure_cycles=bounds[
            "max_consecutive_all_symbol_failure_cycles"
        ],
        v2_spec_path=str(dependency["spec"]),
        v2_spec_sha256=expected_v2_sha,
        live_permission=str(payload.get("live_permission") or ""),
    )
    shadow = ShadowConfig.from_mapping(mechanics, enabled=False)
    collector = DurableCollectorConfigV2(
        enabled=False,
        shadow_enabled=False,
        basis_stress_bps=durable["basis_stress_bps"],
        minimum_expected_edge_bps=durable["minimum_expected_edge_bps"],
    )
    return payload, config, shadow, collector


def _state_checksum(payload: Mapping[str, Any]) -> str:
    core = dict(payload)
    core.pop("state_sha256", None)
    return _sha256(core)


@dataclass
class StationStateV1:
    station_config_sha256: str
    started_at_ms: int
    deadline_at_ms: int
    updated_at_ms: int
    status: str = "ACTIVE"
    stop_reason: Optional[str] = None
    cycle_count: int = 0
    attempt_count: int = 0
    durable_observation_count: int = 0
    consecutive_all_symbol_failure_cycles: int = 0
    successes_by_symbol: dict[str, int] = field(default_factory=dict)
    errors_by_symbol: dict[str, int] = field(default_factory=dict)
    last_error_by_symbol: dict[str, str] = field(default_factory=dict)
    last_observed_at_ms_by_symbol: dict[str, int] = field(default_factory=dict)
    next_funding_time_ms_by_symbol: dict[str, int] = field(default_factory=dict)
    next_due_at_ms: int = 0
    last_action_by_symbol: dict[str, str] = field(default_factory=dict)
    last_record_sha256_by_symbol: dict[str, str] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        core = {
            "schema_id": STATE_SCHEMA_ID,
            **dataclasses.asdict(self),
            "research_only": True,
            "executable": False,
            "broker_calls": False,
            "private_api_calls": False,
            "performance_claims": False,
        }
        core["state_sha256"] = _state_checksum(core)
        return core

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any], *, expected_config_sha256: str) -> "StationStateV1":
        if row.get("schema_id") != STATE_SCHEMA_ID:
            raise CashCarryShadowError("station state schema mismatch")
        if row.get("state_sha256") != _state_checksum(row):
            raise CashCarryShadowError("station state checksum mismatch")
        if row.get("station_config_sha256") != expected_config_sha256:
            raise CashCarryShadowError("station state/config mismatch")
        if not row.get("research_only") or row.get("executable") or row.get("broker_calls"):
            raise CashCarryShadowError("station state safety identity mismatch")
        allowed = {item.name for item in dataclasses.fields(cls)}
        state = cls(**{key: row[key] for key in allowed})
        for name in (
            "started_at_ms",
            "deadline_at_ms",
            "updated_at_ms",
            "cycle_count",
            "attempt_count",
            "durable_observation_count",
            "consecutive_all_symbol_failure_cycles",
            "next_due_at_ms",
        ):
            _nonnegative_int(getattr(state, name), name)
        if state.status not in {"ACTIVE", "PAUSED", "COMPLETED", "BLOCKED"}:
            raise CashCarryShadowError("station state status is invalid")
        return state


class AtomicStationStateStore:
    def __init__(self, path: Path, *, config_sha256: str) -> None:
        self.path = path
        self.config_sha256 = config_sha256

    def load(self) -> Optional[StationStateV1]:
        if not self.path.exists():
            return None
        if stat.S_ISLNK(self.path.lstat().st_mode):
            raise CashCarryShadowError("station state symlink is forbidden")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CashCarryShadowError("station state is corrupt") from exc
        return StationStateV1.from_mapping(
            payload,
            expected_config_sha256=self.config_sha256,
        )

    def save(self, state: StationStateV1) -> None:
        if state.station_config_sha256 != self.config_sha256:
            raise CashCarryShadowError("refusing to save state for another config")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and stat.S_ISLNK(self.path.lstat().st_mode):
            raise CashCarryShadowError("station state symlink is forbidden")
        temporary = self.path.with_name(f".{self.path.name}.tmp.{os.getpid()}")
        if temporary.exists():
            raise CashCarryShadowError("station temporary state already exists")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(temporary, flags, 0o600)
            try:
                os.fchmod(fd, 0o600)
                data = _canonical(state.payload()) + b"\n"
                if os.write(fd, data) != len(data):
                    raise CashCarryShadowError("short station state write")
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, self.path)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            finally:
                raise
        directory_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


@contextmanager
def station_run_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    if stat.S_ISLNK(root.lstat().st_mode):
        raise CashCarryShadowError("station root symlink is forbidden")
    lock_path = root / "station.lock"
    if lock_path.exists() and stat.S_ISLNK(lock_path.lstat().st_mode):
        raise CashCarryShadowError("station lock symlink is forbidden")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CashCarryShadowError("another station process owns this run root") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _tree_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


def _journal_path(root: Path, symbol: str) -> Path:
    return root / "journals" / f"{symbol.lower()}.jsonl"


def _launch_receipt(config: StationConfigV1, root: Path, started_at_ms: int) -> dict[str, Any]:
    return {
        "schema_id": LAUNCH_SCHEMA_ID,
        "research_only": True,
        "executable": False,
        "broker_calls": False,
        "private_api_calls": False,
        "api_keys_or_environment_reads": False,
        "orders_transfers_withdrawals": False,
        "adapter_id": config.adapter_id,
        "exchange_id": config.exchange_id,
        "source_id": config.source_id,
        "public_method": "GET_ONLY",
        "symbols": list(config.symbols),
        "started_at_ms": started_at_ms,
        "deadline_at_ms": started_at_ms + config.max_runtime_seconds * 1000,
        "poll_interval_seconds": config.poll_interval_seconds,
        "funding_capture_delay_seconds": config.funding_capture_delay_seconds,
        "funding_capture_retry_seconds": config.funding_capture_retry_seconds,
        "max_funding_valuation_lag_seconds": config.max_funding_valuation_lag_seconds,
        "max_observations": config.max_observations,
        "max_journal_bytes_per_symbol": config.max_journal_bytes_per_symbol,
        "max_total_bytes": config.max_total_bytes,
        "max_append_reserve_bytes": config.max_append_reserve_bytes,
        "min_free_bytes": config.min_free_bytes,
        "retention_action": "STOP_NO_DELETE_NO_ROTATE",
        "station_config_sha256": config.config_sha256,
        "station_spec_sha256": config.spec_sha256,
        "v2_spec_sha256": config.v2_spec_sha256,
        "run_root": str(root),
        "performance_claims": False,
    }


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and stat.S_ISLNK(path.lstat().st_mode):
        raise CashCarryShadowError("immutable receipt symlink is forbidden")
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if _canonical(existing) != _canonical(payload):
            raise CashCarryShadowError(f"immutable receipt conflict: {path}")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        data = _canonical(payload) + b"\n"
        if os.write(fd, data) != len(data):
            raise CashCarryShadowError("short immutable receipt write")
        os.fsync(fd)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class StationRunResult:
    state: dict[str, Any]
    cycles_this_process: int
    resumed: bool


class PublicCashCarryStationV1:
    def __init__(
        self,
        *,
        config: StationConfigV1,
        shadow_config: ShadowConfig,
        collector_config: DurableCollectorConfigV2,
        adapter: PublicCashCarryAdapter,
        root: Path,
        now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
        sleep: Callable[[float], None] = time.sleep,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    ) -> None:
        self.config = config
        self.shadow_config = dataclasses.replace(shadow_config, enabled=False)
        self.collector_config = collector_config
        self.adapter = adapter
        self.root = root
        self.now_ms = now_ms
        self.sleep = sleep
        self.disk_usage = disk_usage
        if not collector_config.enabled or not collector_config.shadow_enabled:
            raise CashCarryShadowError(
                "station requires explicit durable collector and research-shadow opt-ins"
            )
        if adapter.adapter_id != config.adapter_id or adapter.exchange_id != config.exchange_id:
            raise CashCarryShadowError("station adapter identity differs from frozen spec")
        if adapter.source_id != config.source_id or adapter.public_only is not True:
            raise CashCarryShadowError("station adapter source/public identity mismatch")

    def _journal(self, symbol: str) -> DurableCashCarryJournalV2:
        return DurableCashCarryJournalV2(
            _journal_path(self.root, symbol),
            shadow_config=self.shadow_config,
            collector_config=self.collector_config,
        )

    def _storage_reason(self) -> Optional[str]:
        if _tree_bytes(self.root) + self.config.max_append_reserve_bytes > self.config.max_total_bytes:
            return "max_total_bytes_reached"
        usage = self.disk_usage(self.root)
        if int(usage.free) < self.config.min_free_bytes:
            return "minimum_free_bytes_breached"
        for symbol in self.config.symbols:
            path = _journal_path(self.root, symbol)
            if (
                path.exists()
                and path.stat().st_size + self.config.max_append_reserve_bytes
                > self.config.max_journal_bytes_per_symbol
            ):
                return f"journal_byte_cap_reached:{symbol}"
        return None

    def _reconcile(self, state: StationStateV1) -> None:
        durable = 0
        last_hash: dict[str, str] = {}
        for symbol in self.config.symbols:
            recovered = self._journal(symbol).recover()
            count = int(recovered["record_count"])
            durable += count
            state.successes_by_symbol[symbol] = count
            if recovered["last_record_sha256"]:
                last_hash[symbol] = str(recovered["last_record_sha256"])
        state.durable_observation_count = durable
        state.last_record_sha256_by_symbol = last_hash

    def _next_due(self, state: StationStateV1, now: int, *, any_success: bool) -> int:
        normal = now + self.config.poll_interval_seconds * 1000
        candidates = [
            int(value) + self.config.funding_capture_delay_seconds * 1000
            for value in state.next_funding_time_ms_by_symbol.values()
            if int(value) + self.config.funding_capture_delay_seconds * 1000 > now
        ]
        if not any_success:
            normal = min(normal, now + self.config.transient_retry_seconds * 1000)
        # If a symbol failed in the short post-settlement valuation window,
        # retry that public capture promptly even when other symbols succeeded.
        for symbol in state.last_error_by_symbol:
            funding_at = state.next_funding_time_ms_by_symbol.get(symbol)
            if funding_at is None:
                continue
            lag_ms = now - int(funding_at)
            window_ms = self.config.max_funding_valuation_lag_seconds * 1000
            if 0 <= lag_ms < window_ms:
                retry = now + self.config.funding_capture_retry_seconds * 1000
                if retry - int(funding_at) < window_ms:
                    normal = min(normal, retry)
        return min([normal, *candidates]) if candidates else normal

    def _terminal_reason(self, state: StationStateV1, now: int) -> Optional[str]:
        if now >= state.deadline_at_ms:
            return "max_runtime_reached"
        if state.durable_observation_count >= self.config.max_observations:
            return "max_observations_reached"
        if (
            state.consecutive_all_symbol_failure_cycles
            >= self.config.max_consecutive_all_symbol_failure_cycles
        ):
            return "consecutive_all_symbol_failure_limit_reached"
        return self._storage_reason()

    def _load_or_initialize(self, *, resume_existing: bool) -> tuple[StationStateV1, bool]:
        store = AtomicStationStateStore(
            self.root / "station_state.json",
            config_sha256=self.config.config_sha256,
        )
        state = store.load()
        if state is not None:
            if not resume_existing:
                raise CashCarryShadowError("station state exists; --resume-existing is required")
            if state.status in {"COMPLETED", "BLOCKED"}:
                raise CashCarryShadowError(
                    f"station is terminal ({state.status}:{state.stop_reason}); new run root required"
                )
            state.status = "ACTIVE"
            state.stop_reason = None
            self._reconcile(state)
            state.updated_at_ms = self.now_ms()
            store.save(state)
            return state, True
        now = self.now_ms()
        state = StationStateV1(
            station_config_sha256=self.config.config_sha256,
            started_at_ms=now,
            deadline_at_ms=now + self.config.max_runtime_seconds * 1000,
            updated_at_ms=now,
            successes_by_symbol={symbol: 0 for symbol in self.config.symbols},
            errors_by_symbol={symbol: 0 for symbol in self.config.symbols},
            next_due_at_ms=now,
        )
        _write_immutable_json(
            self.root / "launch_receipt.json",
            _launch_receipt(self.config, self.root, now),
        )
        store.save(state)
        return state, False

    def run(
        self,
        *,
        resume_existing: bool = False,
        max_cycles_this_process: Optional[int] = None,
    ) -> StationRunResult:
        if max_cycles_this_process is not None:
            _positive_int(max_cycles_this_process, "max_cycles_this_process")
        with station_run_lock(self.root):
            store = AtomicStationStateStore(
                self.root / "station_state.json",
                config_sha256=self.config.config_sha256,
            )
            state, resumed = self._load_or_initialize(resume_existing=resume_existing)
            cycles_this_process = 0
            try:
                while True:
                    now = self.now_ms()
                    terminal = self._terminal_reason(state, now)
                    if terminal is not None:
                        blocked = (
                            "byte" in terminal
                            or "failure" in terminal
                            or "free" in terminal
                            or "journal" in terminal
                        )
                        state.status = "BLOCKED" if blocked else "COMPLETED"
                        state.stop_reason = terminal
                        state.updated_at_ms = now
                        store.save(state)
                        break
                    if now < state.next_due_at_ms:
                        self.sleep(min((state.next_due_at_ms - now) / 1000.0, 60.0))
                        continue

                    successes = 0
                    state.cycle_count += 1
                    for symbol in self.config.symbols:
                        if state.durable_observation_count >= self.config.max_observations:
                            break
                        if self.now_ms() >= state.deadline_at_ms:
                            state.status = "COMPLETED"
                            state.stop_reason = "max_runtime_reached"
                            break
                        storage = self._storage_reason()
                        if storage is not None:
                            state.status = "BLOCKED"
                            state.stop_reason = storage
                            break
                        state.attempt_count += 1
                        try:
                            snapshot = self.adapter.fetch(
                                symbol,
                                timeout=self.config.request_timeout_seconds,
                                book_limit=self.config.book_levels,
                            )
                            if snapshot.source != self.config.source_id:
                                raise CashCarryShadowError("snapshot source differs from station source")
                            if snapshot.symbol != symbol:
                                raise CashCarryShadowError("adapter returned the wrong symbol")
                            result = self._journal(symbol).ingest(snapshot)
                            # A valid duplicate remains a successful public
                            # observation; it is merely an idempotent no-op in
                            # the durable journal.
                            successes += 1
                            state.last_action_by_symbol[symbol] = str(result.get("action") or "")
                            state.last_observed_at_ms_by_symbol[symbol] = snapshot.observed_at_ms
                            state.next_funding_time_ms_by_symbol[symbol] = snapshot.next_funding_time_ms
                            state.last_error_by_symbol.pop(symbol, None)
                        except (CashCarryShadowError, OSError, ValueError) as exc:
                            state.errors_by_symbol[symbol] = state.errors_by_symbol.get(symbol, 0) + 1
                            state.last_error_by_symbol[symbol] = f"{type(exc).__name__}: {exc}"[:500]
                        self._reconcile(state)
                        state.updated_at_ms = self.now_ms()
                        store.save(state)
                    if state.status == "BLOCKED":
                        state.updated_at_ms = self.now_ms()
                        store.save(state)
                        break
                    if successes == 0:
                        state.consecutive_all_symbol_failure_cycles += 1
                    else:
                        state.consecutive_all_symbol_failure_cycles = 0
                    now = self.now_ms()
                    state.next_due_at_ms = self._next_due(state, now, any_success=successes > 0)
                    state.updated_at_ms = now
                    store.save(state)
                    cycles_this_process += 1
                    if (
                        max_cycles_this_process is not None
                        and cycles_this_process >= max_cycles_this_process
                    ):
                        state.status = "PAUSED"
                        state.stop_reason = "bounded_process_cycle_limit"
                        state.updated_at_ms = self.now_ms()
                        store.save(state)
                        break
            except KeyboardInterrupt:
                state.status = "PAUSED"
                state.stop_reason = "operator_interrupt"
                state.updated_at_ms = self.now_ms()
                store.save(state)
            return StationRunResult(
                state=state.payload(),
                cycles_this_process=cycles_this_process,
                resumed=resumed,
            )


def read_station_status(
    *,
    root: Path,
    config: StationConfigV1,
    shadow_config: ShadowConfig,
    collector_config: DurableCollectorConfigV2,
) -> dict[str, Any]:
    store = AtomicStationStateStore(
        root / "station_state.json",
        config_sha256=config.config_sha256,
    )
    state = store.load()
    if state is None:
        return {"status": "NOT_STARTED", "run_root": str(root)}
    journals: dict[str, Any] = {}
    active_collector = dataclasses.replace(collector_config, enabled=True, shadow_enabled=True)
    for symbol in config.symbols:
        journal = DurableCashCarryJournalV2(
            _journal_path(root, symbol),
            shadow_config=shadow_config,
            collector_config=active_collector,
        )
        journals[symbol] = journal.recover()
    return {
        "schema_id": "public_cashcarry_station_status_v1",
        "run_root": str(root),
        "state": state.payload(),
        "journals": journals,
        "tree_bytes": _tree_bytes(root),
        "research_only": True,
        "executable": False,
        "network_calls": False,
    }


__all__ = [
    "AtomicStationStateStore",
    "BYBIT_ADAPTER_ID",
    "BYBIT_EXCHANGE_ID",
    "BYBIT_SOURCE_ID",
    "FunctionPublicAdapter",
    "PublicCashCarryAdapter",
    "PublicCashCarryStationV1",
    "StationConfigV1",
    "StationRunResult",
    "StationStateV1",
    "file_sha256",
    "load_station_config",
    "read_station_status",
    "station_run_lock",
]
