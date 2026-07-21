"""Crash-conscious local storage primitives for settlement_execution_v3."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Iterable


class StorageError(RuntimeError):
    """Raised when an on-disk lineage or append-only invariant is violated."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Durably replace *path* using a temp file on the same filesystem."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any) -> str:
    payload = canonical_json_bytes(value)
    atomic_write_bytes(path, payload)
    return sha256_bytes(payload)


def write_immutable_json(path: Path, value: Any) -> str:
    """Create a durable JSON artifact exactly once; never replace it."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise StorageError(f"immutable artifact already exists: {path}") from exc
    _fsync_directory(path.parent)
    return sha256_bytes(payload)


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise StorageError(f"invalid JSON in {path}: {exc}") from exc


def read_verified_json(path: Path, expected_sha256: str) -> Any:
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise StorageError(
            f"artifact hash mismatch for {path}: expected {expected_sha256}, got {actual}"
        )
    return read_json(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.endswith("\n"):
                raise StorageError(
                    f"partial append-only receipt at {path}:{line_number}"
                )
            try:
                row = json.loads(raw)
            except Exception as exc:
                raise StorageError(
                    f"invalid append-only receipt at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise StorageError(
                    f"receipt at {path}:{line_number} is not a JSON object"
                )
            rows.append(row)
    return rows


def _receipt_index(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in rows:
        key = str(row.get("idempotency_key") or "")
        if not key:
            raise StorageError("append-only receipt is missing idempotency_key")
        digest = sha256_json(row)
        previous = index.get(key)
        if previous is not None and previous != digest:
            raise StorageError(f"conflicting receipts for idempotency key {key}")
        index[key] = digest
    return index


def append_jsonl_idempotent(
    path: Path, rows: Iterable[dict[str, Any]]
) -> tuple[int, int]:
    """Append new receipts, skipping exact replays and rejecting conflicts.

    The caller must hold the station-wide flock.  Each row is flushed in one
    append session and the file is fsynced before returning.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(path)
    index = _receipt_index(existing)
    pending: list[bytes] = []
    skipped = 0
    for row in rows:
        key = str(row.get("idempotency_key") or "")
        if not key:
            raise StorageError("new receipt is missing idempotency_key")
        digest = sha256_json(row)
        previous = index.get(key)
        if previous is not None:
            if previous != digest:
                raise StorageError(f"conflicting receipt replay for {key}")
            skipped += 1
            continue
        index[key] = digest
        pending.append(canonical_json_bytes(row))

    if pending:
        with path.open("ab") as handle:
            for payload in pending:
                handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    return len(pending), skipped


class ExclusiveFileLock(AbstractContextManager["ExclusiveFileLock"]):
    """Non-blocking process-wide supervisor lock."""

    def __init__(self, path: Path):
        self.path = path
        self._handle = None

    def __enter__(self) -> "ExclusiveFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+b")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._handle.close()
            self._handle = None
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
