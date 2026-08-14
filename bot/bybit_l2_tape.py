"""Replayable, public-only Bybit L2 and trade tape primitives.

This module intentionally contains no authenticated endpoint, order method, API
key lookup, or strategy decision.  It is the pure/storage half of the public
market-data collector in :mod:`scripts.collect_bybit_l2_tape`.

The persisted contract is deliberately close to the Bybit V5 wire contract:

* every orderbook snapshot/delta keeps ``u`` and ``seq`` plus the unmodified
  decimal price/size strings;
* every public trade keeps exchange ``T``, receive timestamps, trade id and
  message position;
* synthetic ``gap`` records make disconnects and sequence discontinuities
  explicit instead of silently joining invalid book segments;
* append files are UTC-day partitioned and manifests/heartbeats use durable
  temp + fsync + replace writes.

The replay validator is deterministic and does not need network access.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import fcntl
import hashlib
import json
import os
import shutil
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Tuple
from urllib.parse import urlparse


BOOK_SCHEMA = "bybit_l2_book_v1"
TRADE_SCHEMA = "bybit_public_trade_v1"
MANIFEST_SCHEMA = "bybit_l2_tape_manifest_v1"
HEARTBEAT_SCHEMA = "bybit_l2_tape_heartbeat_v1"
DEFAULT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
SUPPORTED_DEPTHS = (50, 200, 1000)


class TapeError(RuntimeError):
    """Base error for collector contract/storage failures."""


class FrameContractError(TapeError):
    """A websocket frame does not satisfy the public tape contract."""


class SequenceGapError(TapeError):
    """A book update cannot be joined to the current snapshot segment."""


class TapeStorageError(TapeError):
    """The append-only store cannot safely persist more data."""


class StorageLimitExceeded(TapeStorageError):
    """The configured disk or free-space limit was reached."""


def utc_now_ms() -> int:
    return time.time_ns() // 1_000_000


def utc_day(value_ms: int) -> str:
    if value_ms <= 0:
        raise ValueError("timestamp must be positive")
    return dt.datetime.fromtimestamp(value_ms / 1000.0, tz=dt.timezone.utc).strftime("%Y%m%d")


def iso_utc(value_ms: int) -> str:
    return (
        dt.datetime.fromtimestamp(value_ms / 1000.0, tz=dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _strict_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise FrameContractError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FrameContractError(f"{field} must be an integer") from exc
    if result < minimum:
        raise FrameContractError(f"{field} must be >= {minimum}")
    return result


def _decimal_string(value: Any, field: str, *, allow_zero: bool) -> str:
    if isinstance(value, bool):
        raise FrameContractError(f"{field} must be decimal text")
    text = str(value)
    try:
        number = decimal.Decimal(text)
    except decimal.InvalidOperation as exc:
        raise FrameContractError(f"{field} is not a decimal") from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        relation = ">= 0" if allow_zero else "> 0"
        raise FrameContractError(f"{field} must be finite and {relation}")
    return text


def normalize_levels(raw: Any, side: str) -> List[List[str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise FrameContractError(f"book {side} must be a list")
    out: List[List[str]] = []
    for index, level in enumerate(raw):
        if not isinstance(level, (list, tuple)) or len(level) != 2:
            raise FrameContractError(f"book {side}[{index}] must be [price,size]")
        out.append(
            [
                _decimal_string(level[0], f"{side}[{index}].price", allow_zero=False),
                _decimal_string(level[1], f"{side}[{index}].size", allow_zero=True),
            ]
        )
    return out


def validate_public_ws_url(url: str) -> str:
    """Reject any private/authenticated/trading websocket surface."""
    parsed = urlparse(str(url))
    if parsed.scheme != "wss" or not parsed.netloc:
        raise ValueError("ws_url must be a wss:// URL")
    if (
        parsed.hostname != "stream.bybit.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("collector permits only the official Bybit mainnet websocket host")
    path = parsed.path.rstrip("/")
    if path != "/v5/public/linear":
        raise ValueError("collector permits only the Bybit V5 public linear websocket path")
    return str(url)


def normalize_symbols(raw: str | Iterable[str]) -> Tuple[str, ...]:
    values = raw.split(",") if isinstance(raw, str) else list(raw)
    symbols: List[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if not symbol:
            continue
        if not symbol.isalnum() or not symbol.endswith("USDT"):
            raise ValueError(f"unsafe/unsupported linear symbol: {symbol!r}")
        if symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise ValueError("at least one symbol is required")
    return tuple(symbols)


def normalize_book_frame(
    message: Mapping[str, Any],
    *,
    recv_ts_ms: int,
    recv_ts_ns: int,
    connection_id: str,
    frame_seq: int,
    depth: int,
) -> Dict[str, Any]:
    topic = str(message.get("topic") or "")
    prefix = f"orderbook.{int(depth)}."
    if not topic.startswith(prefix):
        raise FrameContractError(f"unexpected orderbook topic: {topic!r}")
    data = message.get("data")
    if not isinstance(data, Mapping):
        raise FrameContractError("orderbook data must be an object")
    symbol = str(data.get("s") or topic[len(prefix):]).upper()
    if topic != f"{prefix}{symbol}":
        raise FrameContractError("orderbook topic/data symbol mismatch")
    frame_type = str(message.get("type") or "").lower()
    if frame_type not in {"snapshot", "delta"}:
        raise FrameContractError(f"unsupported orderbook frame type: {frame_type!r}")
    system_ts = _strict_int(message.get("ts"), "book.ts", minimum=1)
    engine_ts = _strict_int(data.get("cts", message.get("cts", system_ts)), "book.cts", minimum=1)
    update_id = _strict_int(data.get("u"), "book.u", minimum=1)
    cross_seq = _strict_int(data.get("seq"), "book.seq", minimum=1)
    return {
        "schema": BOOK_SCHEMA,
        "kind": frame_type,
        "symbol": symbol,
        "depth": int(depth),
        "local_recv_ts_ms": int(recv_ts_ms),
        "local_recv_ts_ns": int(recv_ts_ns),
        "local_recv_iso": iso_utc(int(recv_ts_ms)),
        "exch_ts_ms": engine_ts,
        "system_ts_ms": system_ts,
        "update_id": update_id,
        "seq": cross_seq,
        "connection_id": str(connection_id),
        "connection_frame_seq": int(frame_seq),
        "payload": {
            "b": normalize_levels(data.get("b"), "bids"),
            "a": normalize_levels(data.get("a"), "asks"),
        },
    }


def normalize_trade_frame(
    message: Mapping[str, Any],
    *,
    recv_ts_ms: int,
    recv_ts_ns: int,
    connection_id: str,
    frame_seq: int,
) -> List[Dict[str, Any]]:
    topic = str(message.get("topic") or "")
    prefix = "publicTrade."
    if not topic.startswith(prefix):
        raise FrameContractError(f"unexpected publicTrade topic: {topic!r}")
    topic_symbol = topic[len(prefix):].upper()
    system_ts = _strict_int(message.get("ts"), "trade.ts", minimum=1)
    data = message.get("data")
    if not isinstance(data, list):
        raise FrameContractError("publicTrade data must be a list")
    rows: List[Dict[str, Any]] = []
    previous_exchange_ts: Optional[int] = None
    for index, item in enumerate(data):
        if not isinstance(item, Mapping):
            raise FrameContractError(f"trade data[{index}] must be an object")
        symbol = str(item.get("s") or topic_symbol).upper()
        if symbol != topic_symbol:
            raise FrameContractError("publicTrade topic/data symbol mismatch")
        exchange_ts = _strict_int(item.get("T"), f"trade[{index}].T", minimum=1)
        if previous_exchange_ts is not None and exchange_ts < previous_exchange_ts:
            raise FrameContractError("trades inside one Bybit message are not exchange-time sorted")
        previous_exchange_ts = exchange_ts
        side = str(item.get("S") or "")
        if side not in {"Buy", "Sell"}:
            raise FrameContractError(f"trade[{index}].S must be Buy or Sell")
        trade_id = str(item.get("i") or "")
        if not trade_id:
            raise FrameContractError(f"trade[{index}].i is required")
        rows.append(
            {
                "schema": TRADE_SCHEMA,
                "kind": "trade",
                "symbol": symbol,
                "local_recv_ts_ms": int(recv_ts_ms),
                "local_recv_ts_ns": int(recv_ts_ns),
                "local_recv_iso": iso_utc(int(recv_ts_ms)),
                "exch_ts_ms": exchange_ts,
                "system_ts_ms": system_ts,
                "seq": _strict_int(item.get("seq"), f"trade[{index}].seq", minimum=1),
                "trade_id": trade_id,
                "side": side,
                "price": _decimal_string(item.get("p"), f"trade[{index}].p", allow_zero=False),
                "size": _decimal_string(item.get("v"), f"trade[{index}].v", allow_zero=False),
                "tick_direction": str(item.get("L") or ""),
                "block_trade": bool(item.get("BT", False)),
                "rpi": bool(item.get("RPI", False)),
                "connection_id": str(connection_id),
                "connection_frame_seq": int(frame_seq),
                "message_index": index,
                "message_size": len(data),
            }
        )
    return rows


def marker_record(
    *,
    stream: str,
    symbol: str,
    kind: str,
    reason: str,
    recv_ts_ms: int,
    recv_ts_ns: int,
    connection_id: str,
    frame_seq: int,
    details: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if stream not in {"book", "trades"}:
        raise ValueError("stream must be book or trades")
    if kind not in {"stream_start", "stream_resume", "gap", "stream_stop"}:
        raise ValueError("unsupported marker kind")
    return {
        "schema": BOOK_SCHEMA if stream == "book" else TRADE_SCHEMA,
        "kind": kind,
        "symbol": symbol,
        "local_recv_ts_ms": int(recv_ts_ms),
        "local_recv_ts_ns": int(recv_ts_ns),
        "local_recv_iso": iso_utc(int(recv_ts_ms)),
        "exch_ts_ms": None,
        "seq": None,
        "update_id": None if stream == "book" else None,
        "connection_id": str(connection_id),
        "connection_frame_seq": int(frame_seq),
        "reason": str(reason),
        "details": dict(details or {}),
    }


class BookSequenceTracker:
    """Fail-closed sequence state for one symbol.

    Bybit documents ``u`` as an update id and ``seq`` as a cross sequence, but
    does not contractually guarantee that either increases by exactly one.
    Therefore both must be monotonic within a snapshot segment; transport
    disconnects/runtime failures are the authoritative gap signal.  A fresh
    snapshot resets the segment (including the documented ``u=1`` reset).
    """

    def __init__(self, symbol: str, depth: int, *, resuming_existing_tape: bool = False) -> None:
        self.symbol = symbol
        self.depth = int(depth)
        self.resuming_existing_tape = bool(resuming_existing_tape)
        self.connection_id = ""
        self.segment_index = 0
        self.valid = False
        self.last_update_id: Optional[int] = None
        self.last_seq: Optional[int] = None
        self.started_once = False

    def on_connection_start(
        self, *, connection_id: str, recv_ts_ms: int, recv_ts_ns: int, frame_seq: int
    ) -> Dict[str, Any]:
        resumed = self.started_once or self.resuming_existing_tape
        self.started_once = True
        self.connection_id = connection_id
        self.valid = False
        self.last_update_id = None
        self.last_seq = None
        return marker_record(
            stream="book",
            symbol=self.symbol,
            kind="gap" if resumed else "stream_start",
            reason="websocket_reconnect_waiting_snapshot" if resumed else "collector_start_waiting_snapshot",
            recv_ts_ms=recv_ts_ms,
            recv_ts_ns=recv_ts_ns,
            connection_id=connection_id,
            frame_seq=frame_seq,
            details={"depth": self.depth, "replayable": False},
        )

    def on_disconnect(
        self,
        *,
        reason: str,
        recv_ts_ms: int,
        recv_ts_ns: int,
        connection_id: str,
        frame_seq: int,
    ) -> Dict[str, Any]:
        details = {
            "last_update_id": self.last_update_id,
            "last_seq": self.last_seq,
            "segment_id": self.current_segment_id,
        }
        self.valid = False
        self.last_update_id = None
        self.last_seq = None
        return marker_record(
            stream="book",
            symbol=self.symbol,
            kind="gap",
            reason=reason,
            recv_ts_ms=recv_ts_ms,
            recv_ts_ns=recv_ts_ns,
            connection_id=connection_id,
            frame_seq=frame_seq,
            details=details,
        )

    @property
    def current_segment_id(self) -> Optional[str]:
        if not self.connection_id or self.segment_index <= 0:
            return None
        return f"{self.connection_id}:{self.segment_index}"

    def process(self, record: MutableMapping[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
        if record.get("schema") != BOOK_SCHEMA or record.get("symbol") != self.symbol:
            raise FrameContractError("book record routed to the wrong sequence tracker")
        frame_type = str(record.get("kind") or "")
        update_id = _strict_int(record.get("update_id"), "book.u", minimum=1)
        cross_seq = _strict_int(record.get("seq"), "book.seq", minimum=1)

        if frame_type == "snapshot":
            self.segment_index += 1
            self.valid = True
            self.last_update_id = update_id
            self.last_seq = cross_seq
            record["segment_id"] = self.current_segment_id
            record["replayable"] = True
            record["segment_boundary"] = "snapshot"
            return [dict(record)], False

        if frame_type != "delta":
            raise FrameContractError(f"unexpected tracker frame kind: {frame_type!r}")

        gap_reason: Optional[str] = None
        details: Dict[str, Any] = {}
        if not self.valid or self.last_update_id is None or self.last_seq is None:
            gap_reason = "delta_before_snapshot"
        elif update_id <= self.last_update_id:
            gap_reason = "non_monotonic_update_id"
            details["minimum_update_id"] = self.last_update_id + 1
            details["observed_update_id"] = update_id
        elif cross_seq <= self.last_seq:
            gap_reason = "non_monotonic_cross_sequence"
            details["previous_seq"] = self.last_seq
            details["observed_seq"] = cross_seq

        if gap_reason is not None:
            details.update(
                {
                    "previous_update_id": self.last_update_id,
                    "previous_seq": self.last_seq,
                    "observed_update_id": update_id,
                    "observed_seq": cross_seq,
                    "segment_id": self.current_segment_id,
                }
            )
            gap = marker_record(
                stream="book",
                symbol=self.symbol,
                kind="gap",
                reason=gap_reason,
                recv_ts_ms=int(record["local_recv_ts_ms"]),
                recv_ts_ns=int(record["local_recv_ts_ns"]),
                connection_id=str(record["connection_id"]),
                frame_seq=int(record["connection_frame_seq"]),
                details=details,
            )
            record["segment_id"] = self.current_segment_id
            record["replayable"] = False
            record["invalid_reason"] = gap_reason
            self.valid = False
            self.last_update_id = None
            self.last_seq = None
            return [gap, dict(record)], True

        self.last_update_id = update_id
        self.last_seq = cross_seq
        record["segment_id"] = self.current_segment_id
        record["replayable"] = True
        return [dict(record)], False


def _json_line(payload: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise TapeStorageError(f"record is not canonical JSON: {exc}") from exc
    return encoded


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise TapeStorageError(f"refusing to replace symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    directory_fd: Optional[int] = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600)
        try:
            data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise TapeStorageError("short atomic JSON write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(directory_fd)
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@dataclasses.dataclass
class PartitionStats:
    path: str
    symbol: str
    stream: str
    day: str
    session_records: int = 0
    session_bytes: int = 0
    snapshots: int = 0
    deltas: int = 0
    trades: int = 0
    gaps: int = 0
    min_seq: Optional[int] = None
    max_seq: Optional[int] = None
    min_update_id: Optional[int] = None
    max_update_id: Optional[int] = None
    first_recv_ts_ms: Optional[int] = None
    last_recv_ts_ms: Optional[int] = None
    first_exch_ts_ms: Optional[int] = None
    last_exch_ts_ms: Optional[int] = None
    recovered_partial_tail_bytes: int = 0
    covered_ms: int = 0
    coverage_open_ts_ms: Optional[int] = None
    coverage_closed_ts_ms: Optional[int] = None

    def observe(self, record: Mapping[str, Any], encoded_bytes: int) -> None:
        self.session_records += 1
        self.session_bytes += int(encoded_bytes)
        kind = str(record.get("kind") or "")
        if kind == "snapshot":
            self.snapshots += 1
        elif kind == "delta":
            self.deltas += 1
        elif kind == "trade":
            self.trades += 1
        elif kind == "gap":
            self.gaps += 1
        seq = record.get("seq")
        if isinstance(seq, int):
            self.min_seq = seq if self.min_seq is None else min(self.min_seq, seq)
            self.max_seq = seq if self.max_seq is None else max(self.max_seq, seq)
        update_id = record.get("update_id")
        if isinstance(update_id, int):
            self.min_update_id = update_id if self.min_update_id is None else min(self.min_update_id, update_id)
            self.max_update_id = update_id if self.max_update_id is None else max(self.max_update_id, update_id)
        recv = record.get("local_recv_ts_ms")
        if isinstance(recv, int):
            self.first_recv_ts_ms = recv if self.first_recv_ts_ms is None else min(self.first_recv_ts_ms, recv)
            self.last_recv_ts_ms = recv if self.last_recv_ts_ms is None else max(self.last_recv_ts_ms, recv)
            opens_coverage = (
                (self.stream == "book" and kind == "snapshot" and record.get("replayable") is True)
                or (self.stream == "trades" and kind in {"stream_start", "stream_resume"})
            )
            closes_coverage = kind in {"gap", "stream_stop"}
            if opens_coverage:
                if self.coverage_open_ts_ms is not None:
                    self.covered_ms += max(0, recv - self.coverage_open_ts_ms)
                self.coverage_open_ts_ms = recv
                self.coverage_closed_ts_ms = None
            elif closes_coverage and self.coverage_open_ts_ms is not None:
                self.covered_ms += max(0, recv - self.coverage_open_ts_ms)
                self.coverage_open_ts_ms = None
                self.coverage_closed_ts_ms = recv
        exchange = record.get("exch_ts_ms")
        if isinstance(exchange, int):
            self.first_exch_ts_ms = exchange if self.first_exch_ts_ms is None else min(self.first_exch_ts_ms, exchange)
            self.last_exch_ts_ms = exchange if self.last_exch_ts_ms is None else max(self.last_exch_ts_ms, exchange)


@dataclasses.dataclass
class _OpenPartition:
    fd: int
    path: Path
    symbol: str
    stream: str
    day: str
    records_since_sync: int = 0
    last_sync_monotonic: float = dataclasses.field(default_factory=time.monotonic)


class TapeStore:
    """Single-writer append store with UTC partitions and crash-tail recovery."""

    def __init__(
        self,
        root: Path,
        *,
        fsync_every_records: int = 2000,
        fsync_interval_sec: float = 1.0,
    ) -> None:
        self.root = Path(root)
        self.fsync_every_records = max(1, int(fsync_every_records))
        self.fsync_interval_sec = max(0.01, float(fsync_interval_sec))
        self._lock_fd: Optional[int] = None
        self._open: Dict[Tuple[str, str], _OpenPartition] = {}
        self._stats: Dict[str, PartitionStats] = {}
        self._closed = False

    def acquire(self) -> None:
        if self._lock_fd is not None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise TapeStorageError(f"unsafe tape root: {self.root}")
        lock_path = self.root / ".collector.lock"
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(lock_path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise TapeStorageError("collector lock is not a regular file")
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.write(fd, f"pid={os.getpid()} started_ms={utc_now_ms()}\n".encode("ascii"))
            os.fsync(fd)
        except Exception:
            os.close(fd)
            raise
        self._lock_fd = fd

    def has_existing_tape(self, symbol: str, stream: Optional[str] = None) -> bool:
        symbol_dir = self.root / symbol
        if not symbol_dir.is_dir():
            return False
        suffixes = (
            (f".{stream}.jsonl", f".{stream}.jsonl.zst")
            if stream in {"book", "trades"}
            else (".jsonl", ".jsonl.zst")
        )
        return any(
            child.is_file() and child.name.endswith(suffixes)
            for child in symbol_dir.iterdir()
        )

    def _partition_path(self, symbol: str, stream: str, day: str) -> Path:
        if stream not in {"book", "trades"}:
            raise TapeStorageError("invalid tape stream")
        if not symbol.isalnum() or len(day) != 8 or not day.isdigit():
            raise TapeStorageError("unsafe partition identity")
        return self.root / symbol / f"{day}.{stream}.jsonl"

    @staticmethod
    def _repair_partial_tail(path: Path) -> int:
        if not path.exists() or path.stat().st_size == 0:
            return 0
        with path.open("r+b", buffering=0) as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(size - 1)
            if handle.read(1) == b"\n":
                return 0
            position = size
            keep = 0
            while position > 0:
                start = max(0, position - 1_048_576)
                handle.seek(start)
                block = handle.read(position - start)
                newline = block.rfind(b"\n")
                if newline >= 0:
                    keep = start + newline + 1
                    break
                position = start
            dropped = size - keep
            handle.truncate(keep)
            handle.flush()
            os.fsync(handle.fileno())
            return dropped

    def _open_partition(self, symbol: str, stream: str, day: str, seed_record: Mapping[str, Any]) -> _OpenPartition:
        key = (symbol, stream)
        current = self._open.get(key)
        if current is not None and current.day == day:
            return current
        if current is not None:
            self._close_rotated_partition(current)
            del self._open[key]
        path = self._partition_path(symbol, stream, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.is_symlink():
            raise TapeStorageError(f"unsafe tape partition path: {path}")
        if path.with_suffix(path.suffix + ".zst").exists():
            raise TapeStorageError(f"refusing to append: compressed partition already exists: {path}")
        dropped = self._repair_partial_tail(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise TapeStorageError(f"partition is not a regular file: {path}")
        os.fchmod(fd, 0o600)
        partition = _OpenPartition(fd=fd, path=path, symbol=symbol, stream=stream, day=day)
        self._open[key] = partition
        stats = self._stats.setdefault(
            str(path), PartitionStats(path=str(path), symbol=symbol, stream=stream, day=day)
        )
        if dropped:
            stats.recovered_partial_tail_bytes += dropped
            recovery = marker_record(
                stream=stream,
                symbol=symbol,
                kind="gap",
                reason="recovered_partial_jsonl_tail",
                recv_ts_ms=int(seed_record["local_recv_ts_ms"]),
                recv_ts_ns=int(seed_record["local_recv_ts_ns"]),
                connection_id=str(seed_record.get("connection_id") or "recovery"),
                frame_seq=int(seed_record.get("connection_frame_seq") or 0),
                details={"dropped_partial_bytes": dropped},
            )
            self._write(partition, recovery)
        return partition

    def _write(self, partition: _OpenPartition, record: Mapping[str, Any]) -> None:
        encoded = _json_line(record)
        view = memoryview(encoded)
        while view:
            written = os.write(partition.fd, view)
            if written <= 0:
                raise TapeStorageError("short append write")
            view = view[written:]
        partition.records_since_sync += 1
        stats = self._stats[str(partition.path)]
        stats.observe(record, len(encoded))
        now = time.monotonic()
        if (
            partition.records_since_sync >= self.fsync_every_records
            or now - partition.last_sync_monotonic >= self.fsync_interval_sec
        ):
            os.fsync(partition.fd)
            partition.records_since_sync = 0
            partition.last_sync_monotonic = now

    def append(self, stream: str, record: Mapping[str, Any]) -> Path:
        if self._closed:
            raise TapeStorageError("tape store is closed")
        if self._lock_fd is None:
            raise TapeStorageError("single-writer lock has not been acquired")
        symbol = str(record.get("symbol") or "").upper()
        recv = _strict_int(record.get("local_recv_ts_ms"), "local_recv_ts_ms", minimum=1)
        day = utc_day(recv)
        partition = self._open_partition(symbol, stream, day, record)
        self._write(partition, record)
        return partition.path

    def flush(self) -> None:
        for partition in self._open.values():
            os.fsync(partition.fd)
            partition.records_since_sync = 0
            partition.last_sync_monotonic = time.monotonic()

    @staticmethod
    def _sync_close(partition: _OpenPartition) -> None:
        try:
            os.fsync(partition.fd)
        finally:
            os.close(partition.fd)

    def _close_rotated_partition(self, partition: _OpenPartition) -> None:
        self._sync_close(partition)
        stats = self._stats.get(str(partition.path))
        if stats is not None and stats.coverage_open_ts_ms is not None:
            day_end = int(
                (
                    dt.datetime.strptime(partition.day, "%Y%m%d")
                    .replace(tzinfo=dt.timezone.utc)
                    + dt.timedelta(days=1)
                ).timestamp()
                * 1000
            )
            stats.covered_ms += max(0, day_end - stats.coverage_open_ts_ms)
            stats.coverage_open_ts_ms = None
            stats.coverage_closed_ts_ms = day_end

    def stats_manifest(self, *, now_ms: Optional[int] = None) -> Dict[str, Any]:
        observed_at = int(now_ms or utc_now_ms())
        result: Dict[str, Any] = {}
        for path, stats in sorted(self._stats.items()):
            row = dataclasses.asdict(stats)
            covered = stats.covered_ms
            if stats.coverage_open_ts_ms is not None:
                covered += max(0, observed_at - stats.coverage_open_ts_ms)
            span_start = stats.first_recv_ts_ms
            span_end = max(
                stats.last_recv_ts_ms or 0,
                stats.coverage_closed_ts_ms or 0,
                observed_at if stats.coverage_open_ts_ms is not None else 0,
            )
            span = max(0, span_end - span_start) if span_start is not None else 0
            row["observed_window_ms"] = span
            row["covered_ms_at_manifest"] = covered
            row["coverage_method"] = "book_snapshot_synced_or_trade_ws_connected_over_observed_window"
            row["coverage"] = round(min(1.0, covered / span), 8) if span else 0.0
            try:
                row["file_bytes"] = Path(path).stat().st_size
            except OSError:
                row["file_bytes"] = None
            result[path] = row
        return result

    def rotate_before_day(self, day: str) -> List[Path]:
        """Fsync/close partitions from older UTC days before compression."""
        closed: List[Path] = []
        for key, partition in list(self._open.items()):
            if partition.day < day:
                self._close_rotated_partition(partition)
                closed.append(partition.path)
                del self._open[key]
        return closed

    def close(self) -> None:
        if self._closed:
            return
        errors: List[BaseException] = []
        for partition in list(self._open.values()):
            try:
                self._sync_close(partition)
            except BaseException as exc:  # preserve every fd close attempt
                errors.append(exc)
        self._open.clear()
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = None
        self._closed = True
        if errors:
            raise TapeStorageError(f"failed to close {len(errors)} tape partition(s)")

    def __enter__(self) -> "TapeStore":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


_TAPE_SUFFIXES = (".book.jsonl", ".trades.jsonl", ".book.jsonl.zst", ".trades.jsonl.zst")


def iter_tape_files(root: Path) -> Iterator[Path]:
    root = Path(root)
    if not root.exists():
        return
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        owned_dirs: List[str] = []
        for name in dirs:
            child = current_path / name
            if child.is_symlink():
                continue
            # Multiple collectors may intentionally live below a common
            # runtime/tape parent.  A directory with its own control pair is a
            # separate storage owner; recursing into it makes retention and
            # background compression race the child collector.
            if child != root and (child / "manifest.json").is_file() and (child / "heartbeat.json").is_file():
                continue
            owned_dirs.append(name)
        dirs[:] = owned_dirs
        for name in files:
            path = Path(current) / name
            if name.endswith(_TAPE_SUFFIXES) and not path.is_symlink() and path.is_file():
                yield path


def tape_storage_bytes(root: Path) -> int:
    total = 0
    for path in iter_tape_files(root):
        try:
            total += path.stat().st_size
        except FileNotFoundError:
            # A verified background compressor may atomically replace/unlink a
            # completed JSONL between directory enumeration and stat.
            continue
    return total


def storage_status(root: Path, *, max_disk_bytes: int, min_free_bytes: int) -> Dict[str, Any]:
    root = Path(root)
    probe = root if root.exists() else root.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = tape_storage_bytes(root) if root.exists() else 0
    disk = shutil.disk_usage(probe)
    status = {
        "tape_bytes": usage,
        "max_disk_bytes": int(max_disk_bytes),
        "free_bytes": disk.free,
        "min_free_bytes": int(min_free_bytes),
        "within_tape_cap": usage < int(max_disk_bytes),
        "free_space_ok": disk.free >= int(min_free_bytes),
    }
    status["allowed"] = bool(status["within_tape_cap"] and status["free_space_ok"])
    return status


def enforce_storage_budget(root: Path, *, max_disk_bytes: int, min_free_bytes: int) -> Dict[str, Any]:
    status = storage_status(root, max_disk_bytes=max_disk_bytes, min_free_bytes=min_free_bytes)
    if not status["allowed"]:
        raise StorageLimitExceeded(f"tape storage budget blocked: {status}")
    return status


def _partition_day(path: Path) -> Optional[dt.date]:
    token = path.name.split(".", 1)[0]
    try:
        return dt.datetime.strptime(token, "%Y%m%d").date()
    except ValueError:
        return None


def expired_partition_files(root: Path, *, now_ms: int, retention_days: int) -> List[Path]:
    if retention_days <= 0:
        return []
    today = dt.datetime.fromtimestamp(now_ms / 1000.0, tz=dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=int(retention_days))
    return sorted(path for path in iter_tape_files(root) if (_partition_day(path) or today) < cutoff)


def prune_expired_partitions(root: Path, *, now_ms: int, retention_days: int) -> List[str]:
    """Delete only recognized, completed tape partitions older than retention."""
    deleted: List[str] = []
    for path in expired_partition_files(root, now_ms=now_ms, retention_days=retention_days):
        if path.is_symlink() or not path.is_file() or not path.name.endswith(_TAPE_SUFFIXES):
            raise TapeStorageError(f"unsafe retention candidate: {path}")
        path.unlink()
        deleted.append(str(path))
    return deleted


def compress_jsonl_partition(path: Path, *, level: int = 6) -> Path:
    """Atomically create and verify ``.zst``, then remove the source JSONL."""
    path = Path(path)
    if not path.name.endswith(".jsonl") or path.is_symlink() or not path.is_file():
        raise TapeStorageError(f"unsafe compression source: {path}")
    try:
        import zstandard as zstd  # type: ignore
    except ImportError as exc:  # pragma: no cover - deployment dependency path
        raise TapeStorageError("zstandard is required when compression is enabled") from exc
    target = path.with_suffix(path.suffix + ".zst")
    if target.exists() or target.is_symlink():
        raise TapeStorageError(f"compression target already exists: {target}")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    source_hash = hashlib.sha256()
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        target_fd = os.open(temporary, flags, 0o600)
        with os.fdopen(target_fd, "wb") as raw_target, path.open("rb") as source:
            compressor = zstd.ZstdCompressor(level=int(level))
            with compressor.stream_writer(raw_target, closefd=False) as compressed:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    source_hash.update(block)
                    compressed.write(block)
            raw_target.flush()
            os.fsync(raw_target.fileno())
        os.replace(temporary, target)
        verify_hash = hashlib.sha256()
        with target.open("rb") as raw_source:
            with zstd.ZstdDecompressor().stream_reader(raw_source) as decompressed:
                for block in iter(lambda: decompressed.read(1024 * 1024), b""):
                    verify_hash.update(block)
        if verify_hash.digest() != source_hash.digest():
            target.unlink(missing_ok=True)
            raise TapeStorageError(f"compressed partition verification failed: {path}")
        path.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def completed_uncompressed_partitions(root: Path, *, now_ms: int) -> List[Path]:
    today = utc_day(now_ms)
    return sorted(
        path
        for path in iter_tape_files(root)
        if path.name.endswith(".jsonl") and not path.name.startswith(today)
    )


def compress_completed_partitions(root: Path, *, now_ms: int, level: int = 6) -> List[str]:
    compressed: List[str] = []
    for path in completed_uncompressed_partitions(root, now_ms=now_ms):
        compressed.append(str(compress_jsonl_partition(path, level=level)))
    return compressed


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    path = Path(path)
    if path.name.endswith(".zst"):
        try:
            import zstandard as zstd  # type: ignore
        except ImportError as exc:  # pragma: no cover - deployment dependency path
            raise TapeStorageError("zstandard is required to validate .zst tape") from exc
        with path.open("rb") as raw:
            with zstd.ZstdDecompressor().stream_reader(raw) as stream:
                import io

                with io.TextIOWrapper(stream, encoding="utf-8") as text:
                    for line_number, line in enumerate(text, 1):
                        if line.strip():
                            try:
                                value = json.loads(line)
                            except json.JSONDecodeError as exc:
                                raise TapeStorageError(f"{path}:{line_number}: invalid JSON") from exc
                            if not isinstance(value, dict):
                                raise TapeStorageError(f"{path}:{line_number}: row must be object")
                            yield value
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TapeStorageError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise TapeStorageError(f"{path}:{line_number}: row must be object")
            yield value


def _book_side(levels: Any, side: str) -> Dict[decimal.Decimal, decimal.Decimal]:
    normalized = normalize_levels(levels, side)
    result: Dict[decimal.Decimal, decimal.Decimal] = {}
    for price_text, size_text in normalized:
        price = decimal.Decimal(price_text)
        size = decimal.Decimal(size_text)
        if price in result:
            raise FrameContractError(f"duplicate {side} price in one frame: {price_text}")
        if size > 0:
            result[price] = size
    return result


def _apply_side(book: Dict[decimal.Decimal, decimal.Decimal], levels: Any, side: str) -> None:
    for price_text, size_text in normalize_levels(levels, side):
        price = decimal.Decimal(price_text)
        size = decimal.Decimal(size_text)
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size


def _book_digest(bids: Mapping[decimal.Decimal, decimal.Decimal], asks: Mapping[decimal.Decimal, decimal.Decimal]) -> str:
    canonical = {
        "bids": [[str(price), str(bids[price])] for price in sorted(bids, reverse=True)],
        "asks": [[str(price), str(asks[price])] for price in sorted(asks)],
    }
    return hashlib.sha256(_json_line(canonical)).hexdigest()


class BookReplayValidator:
    def __init__(self, *, expected_symbol: Optional[str] = None, expected_depth: Optional[int] = None) -> None:
        self.expected_symbol = expected_symbol
        self.expected_depth = expected_depth
        self.bids: Dict[decimal.Decimal, decimal.Decimal] = {}
        self.asks: Dict[decimal.Decimal, decimal.Decimal] = {}
        self.valid_segment = False
        self.last_update_id: Optional[int] = None
        self.last_seq: Optional[int] = None
        self.segment_id: Optional[str] = None
        self.records = 0
        self.snapshots = 0
        self.deltas = 0
        self.gaps = 0
        self.invalid_frames = 0
        self.errors: List[str] = []
        self.first_recv_ts_ms: Optional[int] = None
        self.last_recv_ts_ms: Optional[int] = None
        self.last_recv_ts_ns: Optional[int] = None
        self.covered_ms = 0
        self.coverage_started_ms: Optional[int] = None
        self.raw_hash = hashlib.sha256()
        self.recv_days: set[str] = set()

    def _error(self, message: str) -> None:
        self.errors.append(f"record {self.records}: {message}")

    def _close_coverage(self, at_ms: int) -> None:
        if self.coverage_started_ms is not None:
            self.covered_ms += max(0, at_ms - self.coverage_started_ms)
            self.coverage_started_ms = None

    def _validate_book_shape(self) -> None:
        if not self.bids or not self.asks:
            self._error("book has an empty side")
            return
        if max(self.bids) >= min(self.asks):
            self._error("book is crossed or locked")

    def consume(self, record: Mapping[str, Any]) -> None:
        self.records += 1
        self.raw_hash.update(_json_line(record))
        if record.get("schema") != BOOK_SCHEMA:
            self._error("wrong schema")
            return
        symbol = str(record.get("symbol") or "")
        if self.expected_symbol and symbol != self.expected_symbol:
            self._error(f"unexpected symbol {symbol!r}")
        depth = record.get("depth")
        if self.expected_depth is not None and record.get("kind") in {"snapshot", "delta"} and depth != self.expected_depth:
            self._error(f"unexpected depth {depth!r}")
        try:
            recv_ms = _strict_int(record.get("local_recv_ts_ms"), "local_recv_ts_ms", minimum=1)
            recv_ns = _strict_int(record.get("local_recv_ts_ns"), "local_recv_ts_ns", minimum=1)
        except FrameContractError as exc:
            self._error(str(exc))
            return
        if self.last_recv_ts_ns is not None and recv_ns < self.last_recv_ts_ns:
            self._error("local receive timestamp moved backwards")
        self.last_recv_ts_ns = recv_ns
        self.recv_days.add(utc_day(recv_ms))
        self.first_recv_ts_ms = recv_ms if self.first_recv_ts_ms is None else min(self.first_recv_ts_ms, recv_ms)
        self.last_recv_ts_ms = recv_ms if self.last_recv_ts_ms is None else max(self.last_recv_ts_ms, recv_ms)

        kind = str(record.get("kind") or "")
        if kind in {"gap", "stream_start", "stream_resume", "stream_stop"}:
            if kind == "gap":
                self.gaps += 1
            self._close_coverage(recv_ms)
            self.valid_segment = False
            self.last_update_id = None
            self.last_seq = None
            self.segment_id = None
            return
        if kind not in {"snapshot", "delta"}:
            self._error(f"unknown kind {kind!r}")
            return
        replayable = record.get("replayable") is True
        if not replayable:
            self.invalid_frames += 1
            if self.valid_segment:
                self._error("non-replayable frame was not preceded by a gap marker")
            return
        try:
            update_id = _strict_int(record.get("update_id"), "update_id", minimum=1)
            cross_seq = _strict_int(record.get("seq"), "seq", minimum=1)
            payload = record.get("payload")
            if not isinstance(payload, Mapping):
                raise FrameContractError("book payload must be an object")
            if kind == "snapshot":
                self._close_coverage(recv_ms)
                self.bids = _book_side(payload.get("b"), "bids")
                self.asks = _book_side(payload.get("a"), "asks")
                self.snapshots += 1
                self.valid_segment = True
                self.last_update_id = update_id
                self.last_seq = cross_seq
                self.segment_id = str(record.get("segment_id") or "")
                self.coverage_started_ms = recv_ms
                self._validate_book_shape()
                return
            self.deltas += 1
            if not self.valid_segment or self.last_update_id is None or self.last_seq is None:
                self._error("replayable delta without a snapshot")
                return
            if update_id <= self.last_update_id:
                self._error(
                    f"update_id did not increase: previous {self.last_update_id}, got {update_id}"
                )
                self.valid_segment = False
                self._close_coverage(recv_ms)
                return
            if cross_seq <= self.last_seq:
                self._error("cross sequence did not increase")
                self.valid_segment = False
                self._close_coverage(recv_ms)
                return
            if str(record.get("segment_id") or "") != self.segment_id:
                self._error("delta segment_id differs from snapshot")
                self.valid_segment = False
                self._close_coverage(recv_ms)
                return
            _apply_side(self.bids, payload.get("b"), "bids")
            _apply_side(self.asks, payload.get("a"), "asks")
            self.last_update_id = update_id
            self.last_seq = cross_seq
            self._validate_book_shape()
        except FrameContractError as exc:
            self._error(str(exc))
            self.valid_segment = False
            self._close_coverage(recv_ms)

    def result(self) -> Dict[str, Any]:
        final_covered = self.covered_ms
        if self.coverage_started_ms is not None and self.last_recv_ts_ms is not None:
            final_covered += max(0, self.last_recv_ts_ms - self.coverage_started_ms)
        span = 0
        if self.first_recv_ts_ms is not None and self.last_recv_ts_ms is not None:
            span = max(0, self.last_recv_ts_ms - self.first_recv_ts_ms)
        coverage = 1.0 if span == 0 and self.snapshots else (final_covered / span if span else 0.0)
        return {
            "valid": not self.errors,
            "records": self.records,
            "snapshots": self.snapshots,
            "deltas": self.deltas,
            "gaps": self.gaps,
            "invalid_frames": self.invalid_frames,
            "first_recv_ts_ms": self.first_recv_ts_ms,
            "last_recv_ts_ms": self.last_recv_ts_ms,
            "valid_coverage": round(max(0.0, min(1.0, coverage)), 8),
            "final_book_levels": {"bids": len(self.bids), "asks": len(self.asks)},
            "final_book_sha256": _book_digest(self.bids, self.asks),
            "raw_records_sha256": self.raw_hash.hexdigest(),
            "recv_utc_days": sorted(self.recv_days),
            "errors": list(self.errors),
        }


class TradeReplayValidator:
    def __init__(self, *, expected_symbol: Optional[str] = None) -> None:
        self.expected_symbol = expected_symbol
        self.records = 0
        self.trades = 0
        self.gaps = 0
        self.errors: List[str] = []
        self.duplicate_trade_ids: List[str] = []
        self.seen_trade_ids: set[str] = set()
        self.last_recv_ts_ns: Optional[int] = None
        self.first_recv_ts_ms: Optional[int] = None
        self.last_recv_ts_ms: Optional[int] = None
        self.last_message: Optional[Tuple[str, int]] = None
        self.last_message_index = -1
        self.last_message_size: Optional[int] = None
        self.last_exchange_ts_in_message: Optional[int] = None
        self.raw_hash = hashlib.sha256()
        self.unique_hash = hashlib.sha256()
        self.recv_days: set[str] = set()
        self.covered_ms = 0
        self.coverage_started_ms: Optional[int] = None
        self._message_finalized = True

    def _close_coverage(self, at_ms: int) -> None:
        if self.coverage_started_ms is not None:
            self.covered_ms += max(0, at_ms - self.coverage_started_ms)
            self.coverage_started_ms = None

    def _finish_message(self) -> None:
        if self.last_message is None or self._message_finalized:
            return
        if self.last_message_size is None or self.last_message_index != self.last_message_size - 1:
            self._error(
                f"incomplete publicTrade message: last_index={self.last_message_index} "
                f"message_size={self.last_message_size}"
            )
        self._message_finalized = True

    def _error(self, message: str) -> None:
        self.errors.append(f"record {self.records}: {message}")

    def consume(self, record: Mapping[str, Any]) -> None:
        self.records += 1
        self.raw_hash.update(_json_line(record))
        if record.get("schema") != TRADE_SCHEMA:
            self._error("wrong schema")
            return
        symbol = str(record.get("symbol") or "")
        if self.expected_symbol and symbol != self.expected_symbol:
            self._error(f"unexpected symbol {symbol!r}")
        try:
            recv_ms = _strict_int(record.get("local_recv_ts_ms"), "local_recv_ts_ms", minimum=1)
            recv_ns = _strict_int(record.get("local_recv_ts_ns"), "local_recv_ts_ns", minimum=1)
        except FrameContractError as exc:
            self._error(str(exc))
            return
        if self.last_recv_ts_ns is not None and recv_ns < self.last_recv_ts_ns:
            self._error("local receive timestamp moved backwards")
        self.last_recv_ts_ns = recv_ns
        self.recv_days.add(utc_day(recv_ms))
        self.first_recv_ts_ms = recv_ms if self.first_recv_ts_ms is None else min(self.first_recv_ts_ms, recv_ms)
        self.last_recv_ts_ms = recv_ms if self.last_recv_ts_ms is None else max(self.last_recv_ts_ms, recv_ms)
        kind = str(record.get("kind") or "")
        if kind in {"gap", "stream_start", "stream_resume", "stream_stop"}:
            self._finish_message()
            if kind == "gap":
                self.gaps += 1
                self._close_coverage(recv_ms)
            elif kind in {"stream_start", "stream_resume"}:
                self._close_coverage(recv_ms)
                self.coverage_started_ms = recv_ms
            elif kind == "stream_stop":
                self._close_coverage(recv_ms)
            self.last_message = None
            self.last_message_index = -1
            self.last_message_size = None
            self.last_exchange_ts_in_message = None
            return
        if kind != "trade":
            self._error(f"unknown kind {kind!r}")
            return
        self.trades += 1
        try:
            trade_id = str(record.get("trade_id") or "")
            if not trade_id:
                raise FrameContractError("trade_id is required")
            exchange_ts = _strict_int(record.get("exch_ts_ms"), "exch_ts_ms", minimum=1)
            _strict_int(record.get("seq"), "seq", minimum=1)
            _decimal_string(record.get("price"), "price", allow_zero=False)
            _decimal_string(record.get("size"), "size", allow_zero=False)
            if record.get("side") not in {"Buy", "Sell"}:
                raise FrameContractError("side must be Buy or Sell")
            message = (str(record.get("connection_id") or ""), int(record.get("connection_frame_seq") or 0))
            index = int(record.get("message_index"))
            message_size = int(record.get("message_size"))
            if message_size <= 0 or not 0 <= index < message_size:
                raise FrameContractError("message_index/message_size are invalid")
            if message == self.last_message:
                if message_size != self.last_message_size:
                    self._error("message_size changed inside one websocket frame")
                if index != self.last_message_index + 1:
                    self._error("message_index is not contiguous")
                if self.last_exchange_ts_in_message is not None and exchange_ts < self.last_exchange_ts_in_message:
                    self._error("exchange time moved backwards inside one message")
            else:
                self._finish_message()
                if index != 0:
                    self._error("first row of a message must have message_index=0")
                self.last_message = message
                self.last_message_size = message_size
                self._message_finalized = False
            self.last_message_index = index
            self.last_exchange_ts_in_message = exchange_ts
            if trade_id in self.seen_trade_ids:
                self.duplicate_trade_ids.append(trade_id)
            else:
                self.seen_trade_ids.add(trade_id)
                self.unique_hash.update(_json_line(record))
        except (FrameContractError, TypeError, ValueError) as exc:
            self._error(str(exc))

    def result(self) -> Dict[str, Any]:
        self._finish_message()
        final_covered = self.covered_ms
        if self.coverage_started_ms is not None and self.last_recv_ts_ms is not None:
            final_covered += max(0, self.last_recv_ts_ms - self.coverage_started_ms)
        span = 0
        if self.first_recv_ts_ms is not None and self.last_recv_ts_ms is not None:
            span = max(0, self.last_recv_ts_ms - self.first_recv_ts_ms)
        coverage = final_covered / span if span else 0.0
        return {
            "valid": not self.errors,
            "records": self.records,
            "trades": self.trades,
            "gaps": self.gaps,
            "duplicate_trade_count": len(self.duplicate_trade_ids),
            "duplicate_trade_ids_sample": self.duplicate_trade_ids[:20],
            "first_recv_ts_ms": self.first_recv_ts_ms,
            "last_recv_ts_ms": self.last_recv_ts_ms,
            "connected_coverage": round(max(0.0, min(1.0, coverage)), 8),
            "recv_utc_days": sorted(self.recv_days),
            "raw_records_sha256": self.raw_hash.hexdigest(),
            "unique_trades_sha256": self.unique_hash.hexdigest(),
            "errors": list(self.errors),
        }


def validate_tape_file(path: Path, *, symbol: Optional[str] = None, depth: Optional[int] = None) -> Dict[str, Any]:
    path = Path(path)
    stream = "book" if ".book.jsonl" in path.name else "trades" if ".trades.jsonl" in path.name else ""
    if not stream:
        raise TapeStorageError(f"cannot infer tape stream from filename: {path}")
    validator: BookReplayValidator | TradeReplayValidator
    if stream == "book":
        validator = BookReplayValidator(expected_symbol=symbol, expected_depth=depth)
    else:
        validator = TradeReplayValidator(expected_symbol=symbol)
    for row in iter_jsonl(path):
        validator.consume(row)
    result = validator.result()
    result.update({"path": str(path), "stream": stream})
    return result


def select_partition_file(root: Path, *, symbol: str, day: str, stream: str) -> Path:
    base = Path(root) / symbol / f"{day}.{stream}.jsonl"
    compressed = base.with_suffix(base.suffix + ".zst")
    existing = [path for path in (base, compressed) if path.exists()]
    if len(existing) != 1:
        raise TapeStorageError(
            f"expected exactly one {stream} partition for {symbol} {day}; found {[str(p) for p in existing]}"
        )
    return existing[0]


def config_fingerprint(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json_line(config)).hexdigest()
