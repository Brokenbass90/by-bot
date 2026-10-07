"""Single writer, bounded append-only transactions for the isolated observer.

An uncertain append suspends this instance. Reopening verifies the entire bounded
prefix; a partial tail is BLOCKED, never repaired or truncated automatically.
Hashes detect corruption, not malicious replacement by the same OS account.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import stat

from research_lab.os2_shadow_bridge import (
    BridgeBlocked, MAX_BYTES, assess_bundle, canonical, digest, empty_state, identity,
)

MAX_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_RECEIPTS = 4096
MIN_FREE_BYTES = 512 * 1024 * 1024


def strict_json(raw):
    def pairs(items):
        value = {}
        for k, v in items:
            if k in value:
                raise ValueError("duplicate JSON key")
            value[k] = v
        return value
    def nonfinite(_):
        raise ValueError("nonfinite JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def blocked(reason):
    raise BridgeBlocked("BLOCKED_IMPLEMENTATION", reason)


class ShadowJournal:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root_fd = self.lock_fd = self.fd = None
        self.poisoned = False
        self.receipts = {}
        self.state = empty_state()
        self.size = 0
        self.last_hash = "0" * 64
        try:
            if not self.root.is_absolute(): blocked("unsafe_runtime_path")
            for p in (self.root, *self.root.parents):
                if p.is_symlink(): blocked("unsafe_runtime_symlink")
            if not self.root.parent.is_dir(): blocked("runtime_parent_missing")
            self.root.mkdir(mode=0o700, exist_ok=True)
            self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self.root_fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o022: blocked("unsafe_runtime_owner_mode")
            self.root_identity = (info.st_dev, info.st_ino)
            if set(os.listdir(self.root_fd)) - {"writer.lock", "journal.jsonl"}: blocked("runtime_inode_bound")
            self.lock_fd = self._open("writer.lock")
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                blocked("writer_busy")
            self.fd = self._open("journal.jsonl")
            self.file_identity = self._identity(self.fd)
            self.lock_identity = self._identity(self.lock_fd)
            os.fsync(self.root_fd)
            self._load()
            # A prior uncertain complete append is not returned as durable until
            # the verified prefix has been synced successfully on reopen.
            os.fsync(self.fd)
        except Exception as error:
            self.close()
            if isinstance(error, BridgeBlocked): raise
            raise BridgeBlocked("BLOCKED_IMPLEMENTATION", "journal_open_failed") from error

    @staticmethod
    def _identity(fd):
        value = os.fstat(fd)
        if not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid() or value.st_nlink != 1 or value.st_mode & 0o077:
            blocked("unsafe_journal_file")
        return value.st_dev, value.st_ino

    def _open(self, name):
        fd = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.root_fd)
        try:
            self._identity(fd)
            return fd
        except Exception:
            os.close(fd)
            raise

    def _load(self):
        self.size = os.fstat(self.fd).st_size
        if self.size > MAX_JOURNAL_BYTES: blocked("journal_byte_bound")
        raw = os.pread(self.fd, self.size + 1, 0)
        if len(raw) != self.size or (raw and not raw.endswith(b"\n")): blocked("journal_corrupt_prefix")
        for line in raw.splitlines():
            if len(line) > MAX_BYTES or len(self.receipts) >= MAX_RECEIPTS: blocked("receipt_bound")
            try:
                receipt = strict_json(line)
                content = {k: v for k, v in receipt.items() if k != "sha256"}
                valid = (receipt["schema"] == "OS2_SHADOW_RECEIPT_V1"
                         and receipt["sequence"] == len(self.receipts) + 1
                         and receipt["previous_sha256"] == self.last_hash
                         and receipt["sha256"] == digest(content)
                         and identity(receipt["request_id"])
                         and receipt["request_id"] not in self.receipts
                         and receipt["state_after"]["schema"] == "OS2_SHADOW_STATE_V1")
                if not valid: blocked("journal_corrupt_prefix")
            except (ValueError, KeyError, TypeError) as error:
                raise BridgeBlocked("BLOCKED_DATA", "journal_corrupt_prefix") from error
            self.receipts[receipt["request_id"]] = receipt
            self.last_hash = receipt["sha256"]
            self.state = receipt["state_after"]

    def _unchanged(self):
        current_root = os.stat(self.root, follow_symlinks=False)
        if (current_root.st_dev, current_root.st_ino) != self.root_identity: blocked("runtime_changed")
        for name, fd, expected in (("writer.lock", self.lock_fd, self.lock_identity), ("journal.jsonl", self.fd, self.file_identity)):
            path_info = os.stat(name, dir_fd=self.root_fd, follow_symlinks=False)
            if self._identity(fd) != expected or (path_info.st_dev, path_info.st_ino) != expected:
                blocked("journal_changed")
        if set(os.listdir(self.root_fd)) != {"writer.lock", "journal.jsonl"}: blocked("runtime_inode_bound")
        if os.fstat(self.fd).st_size != self.size: blocked("journal_changed")

    def process(self, bundle):
        if self.poisoned: blocked("instance_poisoned")
        self._unchanged()
        try:
            if not isinstance(bundle, dict) or not identity(bundle.get("request_id")):
                raise BridgeBlocked("BLOCKED_DATA", "invalid_request_identity")
            if len(canonical(bundle)) > MAX_BYTES:
                raise BridgeBlocked("BLOCKED_DATA", "input_byte_bound")
            pin = digest(bundle)
        except (ValueError, TypeError) as error:
            raise BridgeBlocked("BLOCKED_DATA", "noncanonical_input") from error
        key = bundle["request_id"]
        if key in self.receipts:
            receipt = self.receipts[key]
            if receipt["input_sha256"] != pin:
                raise BridgeBlocked("BLOCKED_DATA", "request_identity_conflict")
            return strict_json(canonical(receipt))  # Caller cannot mutate in-memory authority.
        if len(self.receipts) >= MAX_RECEIPTS: blocked("receipt_bound")
        result = assess_bundle(bundle, self.state)
        receipt = {"schema": "OS2_SHADOW_RECEIPT_V1", "sequence": len(self.receipts) + 1,
                   "request_id": key, "input_sha256": pin, "previous_sha256": self.last_hash, **result}
        receipt["sha256"] = digest(receipt)
        data = canonical(receipt) + b"\n"
        if len(data) > MAX_BYTES or self.size + len(data) > MAX_JOURNAL_BYTES: blocked("journal_byte_bound")
        if shutil.disk_usage(self.root).free < MIN_FREE_BYTES + len(data): blocked("disk_bound")
        try:
            os.lseek(self.fd, 0, os.SEEK_END)
            written = 0
            while written < len(data):
                count = os.write(self.fd, data[written:])
                if count <= 0: raise OSError("zero append")
                written += count
            os.fsync(self.fd)
        except OSError as error:
            self.poisoned = True
            raise BridgeBlocked("BLOCKED_IMPLEMENTATION", "append_uncertain") from error
        self.size += len(data)
        self.receipts[key] = receipt
        self.last_hash = receipt["sha256"]
        self.state = receipt["state_after"]
        return strict_json(canonical(receipt))

    def close(self):
        for name in ("fd", "lock_fd", "root_fd"):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    def __enter__(self): return self

    def __exit__(self, *_): self.close()
