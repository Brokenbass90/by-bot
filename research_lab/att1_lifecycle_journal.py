"""Bounded immutable event storage for the separate ATT1 zero-risk lifecycle.

Read never creates or repairs evidence. The caller validates domain transitions
before append; returning from append means the complete row is fsynced.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Mapping

GENESIS = '0' * 64
SCHEMA = 'att1_lifecycle_event_v1'


class JournalViolation(ValueError):
    """Evidence, path or durability contract violation; never auto-repair."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise JournalViolation('noncanonical JSON') from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise JournalViolation('duplicate JSON key')
        out[key] = value
    return out


def _constant(value):
    raise JournalViolation('nonfinite JSON constant')


def _event(value: object) -> dict:
    if not isinstance(value, Mapping):
        raise JournalViolation('event must be a JSON object')
    value = dict(value)
    eid = value.get('event_id')
    if value.get('schema_id') != SCHEMA or not isinstance(eid, str) or not 1 <= len(eid) <= 256:
        raise JournalViolation('invalid event identity/schema')
    # Round-trip fixes one JSON representation, avoiding mutable aliases and
    # rejecting key coercion/collisions. Numeric policy belongs to the reducer.
    raw = _canonical(value)
    decoded = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if decoded != value:
        raise JournalViolation('event is not strict JSON')
    return decoded


class LifecycleJournal:
    def __init__(self, path: Path | str, *, max_bytes: int = 67108864,
                 max_record_bytes: int = 1048576):
        for n in (max_bytes, max_record_bytes):
            if type(n) is not int or n <= 0:
                raise JournalViolation('invalid size limit')
        # abspath, not resolve: a symlink must be rejected, never normalized away.
        self.path = Path(os.path.abspath(os.fspath(path)))
        self.max_bytes = max_bytes
        self.max_record_bytes = max_record_bytes

    def _parent(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.path.anchor, flags)
        try:
            for part in self.path.parent.parts[1:]:
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    @contextmanager
    def _locked(self, *, write: bool):
        parent = fd = None
        try:
            parent = self._parent()
            flags = (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK
            created = False
            try:
                fd = os.open(self.path.name, flags, dir_fd=parent)
            except FileNotFoundError:
                if not write:
                    yield None
                    return
                try:
                    fd = os.open(self.path.name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
                    created = True
                except FileExistsError:
                    fd = os.open(self.path.name, flags, dir_fd=parent)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise JournalViolation('journal must be regular single-link file')
            if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
                raise JournalViolation('journal owner/mode must match current user/0600')
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise JournalViolation('journal is locked') from exc
            # Recheck path identity after locking; parent traversal is anchored.
            linked = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
            if (linked.st_dev, linked.st_ino, linked.st_nlink) != (info.st_dev, info.st_ino, 1):
                raise JournalViolation('journal identity changed')
            if created:
                os.fsync(fd)
                os.fsync(parent)
            yield fd
        except OSError as exc:
            raise JournalViolation('journal path/open/durability failure') from exc
        finally:
            if fd is not None:
                os.close(fd)
            if parent is not None:
                os.close(parent)

    def _load(self, fd: int | None):
        if fd is None:
            return [], {}, GENESIS, 0
        size = os.fstat(fd).st_size
        if size > self.max_bytes:
            raise JournalViolation('journal size limit')
        os.lseek(fd, 0, os.SEEK_SET)
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, self.max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_bytes:
                raise JournalViolation('journal size limit')
            chunks.append(chunk)
        raw = b''.join(chunks)
        if len(raw) != size:
            raise JournalViolation('journal size changed while locked')
        if raw and not raw.endswith(b'\n'):
            raise JournalViolation('truncated journal')
        events, identities, tip = [], {}, GENESIS
        for seq, line in enumerate(raw.splitlines(), 1):
            if len(line) + 1 > self.max_record_bytes:
                raise JournalViolation('record size limit')
            try:
                row = json.loads(line.decode('ascii'), object_pairs_hook=_pairs, parse_constant=_constant)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise JournalViolation('invalid journal JSON') from exc
            if not isinstance(row, dict) or set(row) != {'seq', 'prev_hash', 'event', 'event_sha256', 'hash'}:
                raise JournalViolation('invalid row schema')
            if type(row['seq']) is not int or row['seq'] != seq or row['prev_hash'] != tip:
                raise JournalViolation('sequence/hash chain mismatch')
            value = _event(row['event'])
            digest = _hash(value)
            core = {key: val for key, val in row.items() if key != 'hash'}
            if row['event_sha256'] != digest or row['hash'] != _hash(core) or line != _canonical(row):
                raise JournalViolation('event/row hash or canonical bytes mismatch')
            if value['event_id'] in identities:
                raise JournalViolation('duplicate event persisted')
            events.append(value)
            identities[value['event_id']] = _canonical(value)
            tip = row['hash']
        return events, identities, tip, size

    def read(self) -> tuple[dict, ...]:
        with self._locked(write=False) as fd:
            return tuple(self._load(fd)[0])

    def tip(self) -> dict:
        with self._locked(write=False) as fd:
            events, _, tip, _ = self._load(fd)
            return {'rows': len(events), 'tip_hash': tip}

    def append(self, event: Mapping) -> bool:
        return self._append(event, None)[0]

    def append_checked(self, event: Mapping, validate):
        """Validate against latest locked rows, fsync, then return (new, result).

        The trusted pure callback receives all candidate events. It must not
        access this journal recursively. Exceptions leave existing bytes intact.
        """
        if not callable(validate):
            raise JournalViolation('validator must be callable')
        return self._append(event, validate)

    def _append(self, event: Mapping, validate):
        value = _event(event)
        encoded = _canonical(value)
        if len(encoded) > self.max_record_bytes:
            raise JournalViolation('record size limit')
        with self._locked(write=True) as fd:
            events, identities, tip, size = self._load(fd)
            previous = identities.get(value['event_id'])
            if previous is not None:
                if previous != encoded:
                    raise JournalViolation('conflicting event_id')
                return False, validate(tuple(events)) if validate else None
            core = {'seq': len(events) + 1, 'prev_hash': tip, 'event': value,
                    'event_sha256': hashlib.sha256(encoded).hexdigest()}
            row = _canonical({**core, 'hash': _hash(core)}) + b'\n'
            if len(row) > self.max_record_bytes:
                raise JournalViolation('record size limit')
            if size + len(row) > self.max_bytes:
                raise JournalViolation('journal size limit')
            result = validate(tuple(events) + (value,)) if validate else None
            os.lseek(fd, 0, os.SEEK_END)
            offset = 0
            while offset < len(row):
                written = os.write(fd, row[offset:])
                if written <= 0:
                    raise JournalViolation('short journal write')
                offset += written
            os.fsync(fd)
            return True, result
