"""Fail-closed atomic persistence for the research-only MTF long sleeve.

The strategy state and its plan outbox are one immutable JSON envelope.  A
write therefore cannot durably advance the FSM without also durably recording
the plan, or acknowledge a plan without also removing it from the outbox.

This is deliberately a local, single-writer research adapter.  Atomic replace
and optimistic inode checks protect crash consistency, but there is no
interprocess lock; callers must ensure that only one process owns a state file.
"""
from __future__ import annotations

import contextlib
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from strategies.event_expansion_retest_long_mtf_v1 import (
    EventExpansionRetestLongMTFConfigV1,
    MTFContractError,
    MTFOrchestratorStateV1,
    MTFOrchestratorStepV1,
    acknowledge_plan as transition_acknowledge_plan,
    process_closed_m5_prefix,
    state_from_json,
    state_to_json,
)


MAX_STATE_BYTES = 16 * 1024 * 1024


class MTFStatePersistenceError(RuntimeError):
    """The durable state is absent, unsafe, corrupt, or cannot be committed."""


@dataclass(frozen=True)
class _FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _identity(info: os.stat_result) -> _FileIdentity:
    return _FileIdentity(
        device=int(info.st_dev),
        inode=int(info.st_ino),
        size=int(info.st_size),
        mtime_ns=int(info.st_mtime_ns),
    )


class EventExpansionRetestLongMTFStateStore:
    """One-file state+outbox store bound to an exact provider and config."""

    RESEARCH_ONLY = True
    LIVE_READY = False
    SUPPORTS_INTERPROCESS_WRITERS = False

    def __init__(
        self,
        path: Path | str,
        *,
        expected_provider_fingerprint: str,
        expected_cfg: Optional[EventExpansionRetestLongMTFConfigV1] = None,
    ) -> None:
        if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
            raise RuntimeError("host lacks the no-follow directory primitives required by this store")
        raw_path = os.fspath(path)
        if not raw_path:
            raise ValueError("state path must be non-empty")
        # abspath normalizes '.'/'..' without resolving any symlink component.
        self.path = Path(os.path.abspath(raw_path))
        if not self.path.name or self.path.name in {".", ".."}:
            raise ValueError("state path must name a file")
        self.expected_provider_fingerprint = str(expected_provider_fingerprint or "")
        if not _is_sha256(self.expected_provider_fingerprint):
            raise ValueError("expected_provider_fingerprint must be lowercase SHA256")
        self.expected_cfg = expected_cfg or EventExpansionRetestLongMTFConfigV1()
        if not isinstance(self.expected_cfg, EventExpansionRetestLongMTFConfigV1):
            raise TypeError("expected_cfg must be EventExpansionRetestLongMTFConfigV1")

    @contextlib.contextmanager
    def _open_parent_fd(self) -> Iterator[int]:
        """Walk from root with O_NOFOLLOW, never resolving a parent symlink."""
        directory_flags = os.O_RDONLY
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_CLOEXEC", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            current_fd = os.open(os.sep, directory_flags)
        except OSError as exc:  # pragma: no cover - an unusable host filesystem
            raise MTFStatePersistenceError(f"cannot open filesystem root: {exc}") from exc
        try:
            for component in self.path.parent.parts[1:]:
                try:
                    next_fd = os.open(
                        component,
                        directory_flags | nofollow,
                        dir_fd=current_fd,
                    )
                except OSError as exc:
                    raise MTFStatePersistenceError(
                        f"unsafe or missing state parent component {component!r}: {exc}"
                    ) from exc
                os.close(current_fd)
                current_fd = next_fd
            info = os.fstat(current_fd)
            if not stat.S_ISDIR(info.st_mode):
                raise MTFStatePersistenceError("state parent is not a directory")
            yield current_fd
        finally:
            os.close(current_fd)

    def _target_lstat(self, parent_fd: int) -> Optional[os.stat_result]:
        try:
            info = os.stat(self.path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise MTFStatePersistenceError(f"cannot inspect MTF state file: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise MTFStatePersistenceError("refusing MTF state symlink")
        if not stat.S_ISREG(info.st_mode):
            raise MTFStatePersistenceError("MTF state path is not a regular file")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise MTFStatePersistenceError("MTF state file mode must be exactly 0600")
        return info

    def _read_from_parent(
        self, parent_fd: int
    ) -> tuple[Optional[MTFOrchestratorStateV1], Optional[_FileIdentity]]:
        initial = self._target_lstat(parent_fd)
        if initial is None:
            return None, None
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            file_fd = os.open(self.path.name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise MTFStatePersistenceError(f"cannot open MTF state file safely: {exc}") from exc
        try:
            opened = os.fstat(file_fd)
            if not stat.S_ISREG(opened.st_mode):
                raise MTFStatePersistenceError("MTF state path changed to a non-regular file")
            if stat.S_IMODE(opened.st_mode) != 0o600:
                raise MTFStatePersistenceError("MTF state file mode must be exactly 0600")
            if (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino):
                raise MTFStatePersistenceError("MTF state changed while it was being opened")
            if opened.st_size > MAX_STATE_BYTES:
                raise MTFStatePersistenceError("MTF state file exceeds the safety size limit")
            chunks: list[bytes] = []
            remaining = MAX_STATE_BYTES + 1
            while remaining:
                chunk = os.read(file_fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > MAX_STATE_BYTES:
                raise MTFStatePersistenceError("MTF state file exceeds the safety size limit")
        except OSError as exc:
            raise MTFStatePersistenceError(f"cannot read MTF state file: {exc}") from exc
        finally:
            os.close(file_fd)
        try:
            text = raw.decode("utf-8", errors="strict")
            state = state_from_json(
                text,
                expected_provider_fingerprint=self.expected_provider_fingerprint,
                expected_cfg=self.expected_cfg,
            )
        except (UnicodeDecodeError, MTFContractError) as exc:
            raise MTFStatePersistenceError(f"persisted MTF state is invalid: {exc}") from exc
        return state, _identity(opened)

    def load(self) -> Optional[MTFOrchestratorStateV1]:
        """Load a valid pinned state, return None only when no file exists."""
        with self._open_parent_fd() as parent_fd:
            state, _ = self._read_from_parent(parent_fd)
            return state

    def _serialize_validated(self, state: MTFOrchestratorStateV1) -> bytes:
        try:
            text = state_to_json(state)
            restored = state_from_json(
                text,
                expected_provider_fingerprint=self.expected_provider_fingerprint,
                expected_cfg=self.expected_cfg,
            )
        except (MTFContractError, AttributeError, TypeError, ValueError) as exc:
            raise MTFStatePersistenceError(f"refusing invalid MTF state save: {exc}") from exc
        if restored != state:
            raise MTFStatePersistenceError("MTF state did not survive its canonical round trip")
        return text.encode("utf-8")

    @staticmethod
    def _validate_transition(
        previous: Optional[MTFOrchestratorStateV1],
        updated: MTFOrchestratorStateV1,
    ) -> None:
        if previous is None:
            return
        fixed_previous = (
            previous.schema,
            previous.strategy,
            previous.symbol,
            previous.side_identity,
            previous.provider_identity,
            previous.provider_fingerprint,
            previous.config_sha256,
            previous.aggregation_config_fingerprints,
            previous.source_start_open_ts_ms,
        )
        fixed_updated = (
            updated.schema,
            updated.strategy,
            updated.symbol,
            updated.side_identity,
            updated.provider_identity,
            updated.provider_fingerprint,
            updated.config_sha256,
            updated.aggregation_config_fingerprints,
            updated.source_start_open_ts_ms,
        )
        if fixed_previous != fixed_updated:
            raise MTFStatePersistenceError("refusing MTF identity/config/source-start replacement")
        if (
            updated.source_count < previous.source_count
            or updated.m5_watermark_close_ms < previous.m5_watermark_close_ms
            or updated.m15_watermark_close_ms < previous.m15_watermark_close_ms
            or updated.h1_watermark_close_ms < previous.h1_watermark_close_ms
        ):
            raise MTFStatePersistenceError("refusing MTF watermark/source regression")
        if updated.source_count == previous.source_count and updated.source_sha256 != previous.source_sha256:
            raise MTFStatePersistenceError("refusing same-span MTF source mutation")
        if not set(previous.seen_event_ids).issubset(updated.seen_event_ids):
            raise MTFStatePersistenceError("refusing seen-event ledger regression")
        if not set(previous.consumed_retest_ids).issubset(updated.consumed_retest_ids):
            raise MTFStatePersistenceError("refusing consumed-retest ledger regression")
        if not set(previous.acknowledged_plan_ids).issubset(updated.acknowledged_plan_ids):
            raise MTFStatePersistenceError("refusing acknowledged-plan ledger regression")
        previous_plans = {item.plan_id for item in previous.plan_outbox}
        updated_plans = {item.plan_id for item in updated.plan_outbox}
        newly_acknowledged = (
            set(updated.acknowledged_plan_ids) - set(previous.acknowledged_plan_ids)
        )
        if not newly_acknowledged.issubset(previous_plans):
            raise MTFStatePersistenceError("refusing acknowledgement without a prior outbox plan")
        durable_plans = updated_plans | set(updated.acknowledged_plan_ids)
        if not previous_plans.issubset(durable_plans):
            raise MTFStatePersistenceError("refusing to drop an outbox plan without acknowledgement")
        previous_plan_objects = {item.plan_id: item for item in previous.plan_outbox}
        updated_plan_objects = {item.plan_id: item for item in updated.plan_outbox}
        if any(
            updated_plan_objects[plan_id] != previous_plan_objects[plan_id]
            for plan_id in previous_plans & updated_plans
        ):
            raise MTFStatePersistenceError("refusing mutation of a pending outbox plan")
        if previous.plan_outbox and (
            updated.source_count != previous.source_count
            or updated.m5_watermark_close_ms != previous.m5_watermark_close_ms
            or updated.m15_watermark_close_ms != previous.m15_watermark_close_ms
            or updated.h1_watermark_close_ms != previous.h1_watermark_close_ms
        ):
            raise MTFStatePersistenceError(
                "pending MTF outbox must be durably acknowledged before source advancement"
            )

    def _assert_target_unchanged(
        self, parent_fd: int, expected: Optional[_FileIdentity]
    ) -> None:
        current = self._target_lstat(parent_fd)
        if expected is None:
            if current is not None:
                raise MTFStatePersistenceError("MTF state appeared during atomic save")
            return
        if current is None or _identity(current) != expected:
            raise MTFStatePersistenceError("MTF state changed during atomic save")

    def _atomic_write(
        self,
        parent_fd: int,
        data: bytes,
        *,
        expected_identity: Optional[_FileIdentity],
    ) -> None:
        temporary_name = f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        write_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        temporary_fd: Optional[int] = None
        try:
            temporary_fd = os.open(temporary_name, write_flags, 0o600, dir_fd=parent_fd)
            os.fchmod(temporary_fd, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(temporary_fd, view)
                if written <= 0:  # pragma: no cover - os.write either progresses or raises
                    raise OSError("short write while persisting MTF state")
                view = view[written:]
            os.fsync(temporary_fd)
            temp_info = os.fstat(temporary_fd)
            if not stat.S_ISREG(temp_info.st_mode) or stat.S_IMODE(temp_info.st_mode) != 0o600:
                raise MTFStatePersistenceError("atomic MTF temporary file is unsafe")
            os.close(temporary_fd)
            temporary_fd = None
            self._assert_target_unchanged(parent_fd, expected_identity)
            os.replace(
                temporary_name,
                self.path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            # Replacement and directory entry must be durable before returning.
            os.fsync(parent_fd)
            final_info = self._target_lstat(parent_fd)
            if final_info is None:  # pragma: no cover - impossible without external mutation
                raise MTFStatePersistenceError("atomic MTF replace produced no state file")
        except MTFStatePersistenceError:
            raise
        except OSError as exc:
            raise MTFStatePersistenceError(f"atomic MTF state write failed: {exc}") from exc
        finally:
            if temporary_fd is not None:
                os.close(temporary_fd)
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise MTFStatePersistenceError(
                    f"cannot clean failed MTF temporary state: {exc}"
                ) from exc

    def _save_with_parent(
        self,
        parent_fd: int,
        state: MTFOrchestratorStateV1,
        *,
        previous: Optional[MTFOrchestratorStateV1],
        previous_identity: Optional[_FileIdentity],
    ) -> None:
        data = self._serialize_validated(state)
        self._validate_transition(previous, state)
        self._atomic_write(parent_fd, data, expected_identity=previous_identity)

    def save(self, state: MTFOrchestratorStateV1) -> None:
        """Atomically save state and outbox after validating any current file."""
        with self._open_parent_fd() as parent_fd:
            previous, previous_identity = self._read_from_parent(parent_fd)
            self._save_with_parent(
                parent_fd,
                state,
                previous=previous,
                previous_identity=previous_identity,
            )

    def acknowledge_plan(self, plan_id: str) -> MTFOrchestratorStateV1:
        """Durably move exactly one outbox plan to the ack ledger, then return."""
        with self._open_parent_fd() as parent_fd:
            previous, previous_identity = self._read_from_parent(parent_fd)
            if previous is None:
                raise MTFStatePersistenceError("cannot acknowledge a plan without durable MTF state")
            try:
                updated = transition_acknowledge_plan(previous, str(plan_id))
            except MTFContractError as exc:
                raise MTFStatePersistenceError(f"MTF plan acknowledgement rejected: {exc}") from exc
            self._save_with_parent(
                parent_fd,
                updated,
                previous=previous,
                previous_identity=previous_identity,
            )
            persisted, _ = self._read_from_parent(parent_fd)
            if persisted != updated:
                raise MTFStatePersistenceError("persisted MTF acknowledgement verification failed")
            return persisted


class PersistedEventExpansionRetestLongMTFV1Research:
    """Research-only causal orchestrator with one atomic state/outbox owner."""

    RESEARCH_ONLY = True
    LIVE_READY = False
    PERFORMANCE_READY = False
    SUPPORTS_INTERPROCESS_WRITERS = False

    def __init__(
        self,
        *,
        state_path: Path | str,
        provider_identity: str,
        provider_fingerprint: str,
        cfg: Optional[EventExpansionRetestLongMTFConfigV1] = None,
    ) -> None:
        self.provider_identity = str(provider_identity)
        if not self.provider_identity:
            raise ValueError("provider_identity must be non-empty")
        self.cfg = cfg or EventExpansionRetestLongMTFConfigV1()
        self.state_store = EventExpansionRetestLongMTFStateStore(
            state_path,
            expected_provider_fingerprint=provider_fingerprint,
            expected_cfg=self.cfg,
        )

    def process_closed_m5(
        self,
        symbol: str,
        raw_closed_m5: Sequence[Sequence[Any]],
        *,
        as_of_ms: int,
    ) -> MTFOrchestratorStepV1:
        prior = self.state_store.load()
        if prior is not None and prior.plan_outbox:
            raise MTFStatePersistenceError(
                "pending MTF outbox must be consumed and durably acknowledged before replay"
            )
        step = process_closed_m5_prefix(
            symbol,
            raw_closed_m5,
            as_of_ms=as_of_ms,
            provider_identity=self.provider_identity,
            provider_fingerprint=self.state_store.expected_provider_fingerprint,
            prior=prior,
            cfg=self.cfg,
        )
        self.state_store.save(step.state)
        return step

    def pending_plans(self):
        """Return the durable research outbox without advancing any watermark."""
        state = self.state_store.load()
        return () if state is None else state.plan_outbox

    def acknowledge_plan(self, plan_id: str) -> MTFOrchestratorStateV1:
        return self.state_store.acknowledge_plan(plan_id)


__all__ = [
    "EventExpansionRetestLongMTFStateStore",
    "MAX_STATE_BYTES",
    "MTFStatePersistenceError",
    "PersistedEventExpansionRetestLongMTFV1Research",
]
