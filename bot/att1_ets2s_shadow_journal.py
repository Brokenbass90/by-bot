"""Fail-closed hash-chained journal for the ATT1+ETS2S public shadow."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Mapping


GENESIS_HASH = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CLAIM = re.compile(
    r"decision:(?:ALPHA_FORWARD_BACKFILL|EXECUTION_FORWARD):(ATT1|ETS2S):[A-Z0-9]{2,40}:[0-9]+\Z"
)


class JournalViolation(ValueError):
    """Stable fail-closed error for journal safety or integrity drift."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise JournalViolation("noncanonical journal payload") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class HashChainedJournal:
    """Single-writer append-only JSONL with immutable claim semantics."""

    def __init__(self, path: Path | str):
        self.path = Path(os.path.abspath(os.fspath(path)))

    def _open_parent_fd(self) -> int:
        parent = self.path.parent
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        directory = getattr(os, "O_DIRECTORY", 0)
        try:
            current_fd = os.open(parent.anchor or "/", flags | directory)
            for part in parent.parts[1:]:
                next_fd = os.open(part, flags | directory, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
            if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
                os.close(current_fd)
                raise JournalViolation("journal parent is not a directory")
            return current_fd
        except JournalViolation:
            raise
        except OSError as exc:
            try:
                os.close(current_fd)
            except (OSError, UnboundLocalError):
                pass
            raise JournalViolation("journal parent open failed") from exc

    def _open_locked(self) -> tuple[int, int]:
        parent_fd = self._open_parent_fd()
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        created = False
        try:
            try:
                file_fd = os.open(
                    self.path.name,
                    flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_fd,
                )
                created = True
                os.fchmod(file_fd, 0o600)
            except FileExistsError:
                file_fd = os.open(self.path.name, flags, dir_fd=parent_fd)
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode):
                os.close(file_fd)
                raise JournalViolation("journal file is not regular")
            if stat.S_IMODE(info.st_mode) != 0o600:
                os.close(file_fd)
                raise JournalViolation("journal file mode must be 0600")
            try:
                fcntl.flock(file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(file_fd)
                raise JournalViolation("journal is locked") from exc
            if created:
                os.fsync(file_fd)
                os.fsync(parent_fd)
            return file_fd, parent_fd
        except JournalViolation:
            os.close(parent_fd)
            raise
        except IsADirectoryError as exc:
            os.close(parent_fd)
            raise JournalViolation("journal file is not regular") from exc
        except OSError as exc:
            os.close(parent_fd)
            if exc.errno == errno.ELOOP:
                raise JournalViolation("journal path is a symlink") from exc
            raise JournalViolation("journal open failed") from exc

    @staticmethod
    def _read_bytes(file_fd: int) -> bytes:
        try:
            os.lseek(file_fd, 0, os.SEEK_SET)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        except OSError as exc:
            raise JournalViolation("journal read failed") from exc

    @staticmethod
    def _validate_bytes(data: bytes) -> tuple[list[dict[str, object]], dict[str, dict[str, object]], str]:
        if data and not data.endswith(b"\n"):
            raise JournalViolation("truncated journal")
        rows: list[dict[str, object]] = []
        claims: dict[str, dict[str, object]] = {}
        previous = GENESIS_HASH
        for line_no, encoded in enumerate(data.splitlines(), 1):
            try:
                row = json.loads(encoded.decode("ascii"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise JournalViolation(f"corrupt journal line {line_no}") from exc
            if not isinstance(row, dict):
                raise JournalViolation(f"corrupt journal line {line_no}")
            claim = row.get("claim_key")
            row_hash = row.get("row_hash")
            if not isinstance(claim, str) or _CLAIM.fullmatch(claim) is None:
                raise JournalViolation(f"invalid journal claim line {line_no}")
            if row.get("prev_hash") != previous or not isinstance(row_hash, str) or _SHA256.fullmatch(row_hash) is None:
                raise JournalViolation(f"broken journal chain line {line_no}")
            unsigned = {key: value for key, value in row.items() if key != "row_hash"}
            if _digest(unsigned) != row_hash:
                raise JournalViolation(f"broken journal hash line {line_no}")
            core = {key: value for key, value in row.items() if key not in {"prev_hash", "row_hash"}}
            if claim in claims:
                raise JournalViolation(f"duplicate journal claim line {line_no}")
            claims[claim] = core
            rows.append(row)
            previous = row_hash
        return rows, claims, previous

    def _snapshot(self) -> tuple[list[dict[str, object]], dict[str, dict[str, object]], str]:
        file_fd, parent_fd = self._open_locked()
        try:
            return self._validate_bytes(self._read_bytes(file_fd))
        finally:
            fcntl.flock(file_fd, fcntl.LOCK_UN)
            os.close(file_fd)
            os.close(parent_fd)

    def tip(self) -> dict[str, object]:
        rows, _claims, tip_hash = self._snapshot()
        return {"row_count": len(rows), "tip_hash": tip_hash}

    def contains(self, claim_key: str) -> bool:
        _rows, claims, _tip_hash = self._snapshot()
        return claim_key in claims

    def claim_keys(self) -> frozenset[str]:
        _rows, claims, _tip_hash = self._snapshot()
        return frozenset(claims)

    def append(self, payload: Mapping[str, object]) -> bool:
        core = dict(payload)
        if "prev_hash" in core or "row_hash" in core:
            raise JournalViolation("caller supplied chain fields")
        claim = core.get("claim_key")
        if not isinstance(claim, str) or _CLAIM.fullmatch(claim) is None:
            raise JournalViolation("invalid journal claim")
        _canonical(core)
        file_fd, parent_fd = self._open_locked()
        try:
            _rows, claims, tip_hash = self._validate_bytes(self._read_bytes(file_fd))
            if claim in claims:
                if claims[claim] == core:
                    return False
                raise JournalViolation("journal claim conflict")
            unsigned = {**core, "prev_hash": tip_hash}
            row = {**unsigned, "row_hash": _digest(unsigned)}
            encoded = _canonical(row) + b"\n"
            os.lseek(file_fd, 0, os.SEEK_END)
            view = memoryview(encoded)
            while view:
                view = view[os.write(file_fd, view) :]
            os.fsync(file_fd)
            os.fsync(parent_fd)
            return True
        except OSError as exc:
            raise JournalViolation("journal append failed") from exc
        finally:
            fcntl.flock(file_fd, fcntl.LOCK_UN)
            os.close(file_fd)
            os.close(parent_fd)


__all__ = ["GENESIS_HASH", "HashChainedJournal", "JournalViolation"]
