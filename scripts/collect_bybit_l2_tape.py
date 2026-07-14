#!/usr/bin/env python3
"""Collect replayable Bybit public L2 + publicTrade tape (no keys/orders).

Only ``wss://.../v5/public/linear`` is accepted.  The process never imports an
exchange trading client, reads API-key environment variables, or calls a REST
endpoint.  Sequence discontinuities and websocket downtime are persisted as
explicit gap markers; a fresh exchange snapshot is required before book replay
continues.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import importlib.util
import json
import random
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_l2_tape import (  # noqa: E402
    DEFAULT_WS_URL,
    HEARTBEAT_SCHEMA,
    MANIFEST_SCHEMA,
    SUPPORTED_DEPTHS,
    BookSequenceTracker,
    FrameContractError,
    SequenceGapError,
    StorageLimitExceeded,
    TapeError,
    TapeStore,
    atomic_write_json,
    completed_uncompressed_partitions,
    compress_completed_partitions,
    config_fingerprint,
    enforce_storage_budget,
    marker_record,
    normalize_book_frame,
    normalize_symbols,
    normalize_trade_frame,
    prune_expired_partitions,
    storage_status,
    utc_day,
    utc_now_ms,
    validate_public_ws_url,
)

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover - exercised by deployment preflight
    websockets = None


DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT"


class UtcRotationReconnect(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class CollectorConfig:
    symbols: Tuple[str, ...]
    streams: Tuple[str, ...]
    depth: int
    ws_url: str
    root: Path
    duration_sec: float
    chunk_size: int
    ping_interval_sec: float
    ping_timeout_sec: float
    idle_timeout_sec: float
    reconnect_initial_sec: float
    reconnect_max_sec: float
    heartbeat_interval_sec: float
    maintenance_interval_sec: float
    fsync_every_records: int
    fsync_interval_sec: float
    max_queue: int
    max_disk_bytes: int
    min_free_bytes: int
    retention_days: int
    retention_mode: str
    compress_rotated: bool
    compression_level: int
    coverage_alert_below: float

    def public_dict(self) -> Dict[str, Any]:
        """Durable config receipt.  There are deliberately no secret fields."""
        return {
            "symbols": list(self.symbols),
            "streams": list(self.streams),
            "depth": self.depth,
            "ws_url": self.ws_url,
            "root": str(self.root),
            "duration_sec": self.duration_sec,
            "chunk_size": self.chunk_size,
            "ping_interval_sec": self.ping_interval_sec,
            "ping_timeout_sec": self.ping_timeout_sec,
            "idle_timeout_sec": self.idle_timeout_sec,
            "reconnect_initial_sec": self.reconnect_initial_sec,
            "reconnect_max_sec": self.reconnect_max_sec,
            "heartbeat_interval_sec": self.heartbeat_interval_sec,
            "maintenance_interval_sec": self.maintenance_interval_sec,
            "fsync_every_records": self.fsync_every_records,
            "fsync_interval_sec": self.fsync_interval_sec,
            "max_queue": self.max_queue,
            "max_disk_bytes": self.max_disk_bytes,
            "min_free_bytes": self.min_free_bytes,
            "retention_days": self.retention_days,
            "retention_mode": self.retention_mode,
            "compress_rotated": self.compress_rotated,
            "compression_level": self.compression_level,
            "coverage_alert_below": self.coverage_alert_below,
            "public_only": True,
            "authentication": False,
            "order_capability": False,
        }


def _positive(value: float, name: str, *, allow_zero: bool = False) -> float:
    minimum_ok = value >= 0 if allow_zero else value > 0
    if not minimum_ok:
        relation = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be {relation}")
    return value


def config_from_args(args: argparse.Namespace) -> CollectorConfig:
    symbols = normalize_symbols(args.symbols)
    if len(symbols) > int(args.max_symbols):
        raise ValueError(f"symbol count {len(symbols)} exceeds --max-symbols={args.max_symbols}")
    depth = int(args.depth)
    if depth not in SUPPORTED_DEPTHS:
        raise ValueError(f"depth must be one of {SUPPORTED_DEPTHS}")
    requested_streams = tuple(
        stream.strip().lower() for stream in str(args.streams).split(",") if stream.strip()
    )
    if not requested_streams or any(stream not in {"book", "trades"} for stream in requested_streams):
        raise ValueError("streams must be book,trades, book, or trades")
    streams = tuple(stream for stream in ("book", "trades") if stream in requested_streams)
    if "book" in streams and len(symbols) > int(args.max_book_symbols):
        raise ValueError(
            f"book symbol count {len(symbols)} exceeds --max-book-symbols={args.max_book_symbols}; "
            "use --streams trades for a wider microcap tape"
        )
    root = Path(args.root).expanduser().resolve(strict=False)
    if root == Path(root.anchor) or len(root.parts) < 3:
        raise ValueError(f"unsafe tape root: {root}")
    retention_mode = str(args.retention_mode)
    if retention_mode not in {"stop", "delete"}:
        raise ValueError("retention-mode must be stop or delete")
    coverage = float(args.coverage_alert_below)
    if not 0 < coverage <= 1:
        raise ValueError("coverage-alert-below must be in (0,1]")
    reconnect_initial = _positive(float(args.reconnect_initial_sec), "reconnect-initial-sec")
    reconnect_max = _positive(float(args.reconnect_max_sec), "reconnect-max-sec")
    if reconnect_initial > reconnect_max:
        raise ValueError("reconnect-initial-sec cannot exceed reconnect-max-sec")
    return CollectorConfig(
        symbols=symbols,
        streams=streams,
        depth=depth,
        ws_url=validate_public_ws_url(args.ws_url),
        root=root,
        duration_sec=_positive(float(args.duration_sec), "duration-sec", allow_zero=True),
        chunk_size=max(1, int(args.chunk_size)),
        ping_interval_sec=_positive(float(args.ping_interval_sec), "ping-interval-sec"),
        ping_timeout_sec=_positive(float(args.ping_timeout_sec), "ping-timeout-sec"),
        idle_timeout_sec=_positive(float(args.idle_timeout_sec), "idle-timeout-sec"),
        reconnect_initial_sec=reconnect_initial,
        reconnect_max_sec=reconnect_max,
        heartbeat_interval_sec=_positive(float(args.heartbeat_interval_sec), "heartbeat-interval-sec"),
        maintenance_interval_sec=_positive(float(args.maintenance_interval_sec), "maintenance-interval-sec"),
        fsync_every_records=max(1, int(args.fsync_every_records)),
        fsync_interval_sec=_positive(float(args.fsync_interval_sec), "fsync-interval-sec"),
        max_queue=max(1, int(args.max_queue)),
        max_disk_bytes=int(_positive(float(args.max_disk_gb), "max-disk-gb") * 1024**3),
        min_free_bytes=int(_positive(float(args.min_free_gb), "min-free-gb", allow_zero=True) * 1024**3),
        retention_days=max(1, int(args.retention_days)),
        retention_mode=retention_mode,
        compress_rotated=bool(args.compress_rotated),
        compression_level=int(args.compression_level),
        coverage_alert_below=coverage,
    )


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def preflight(config: CollectorConfig) -> Dict[str, Any]:
    checks = {
        "websockets_available": websockets is not None,
        "zstandard_available": importlib.util.find_spec("zstandard") is not None,
        "public_ws_path_only": True,
        "api_keys_read": False,
        "network_calls": False,
        "files_written": False,
    }
    blockers: List[str] = []
    if not checks["websockets_available"]:
        blockers.append("missing_python_dependency:websockets")
    if config.compress_rotated and not checks["zstandard_available"]:
        blockers.append("missing_python_dependency:zstandard")
    try:
        disk = storage_status(
            config.root,
            max_disk_bytes=config.max_disk_bytes,
            min_free_bytes=config.min_free_bytes,
        )
    except OSError as exc:
        disk = {"allowed": False, "error": str(exc)}
        blockers.append("storage_probe_failed")
    if not disk.get("allowed", False):
        blockers.append("storage_budget_blocked")
    return {
        "kind": "bybit_l2_tape_collector_preflight_v1",
        "ok": not blockers,
        "blockers": blockers,
        "checks": checks,
        "storage": disk,
        "config": config.public_dict(),
        "config_sha256": config_fingerprint(config.public_dict()),
    }


class CollectorRuntime:
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config
        self.collector_id = f"l2tape-{utc_now_ms()}-{uuid.uuid4().hex[:12]}"
        self.store = TapeStore(
            config.root,
            fsync_every_records=config.fsync_every_records,
            fsync_interval_sec=config.fsync_interval_sec,
        )
        self.trackers: Dict[str, BookSequenceTracker] = {}
        self.existing_tape: Dict[Tuple[str, str], bool] = {}
        self.connection_count = 0
        self.connection_id = ""
        self.connection_frame_seq = 0
        self.streams_started = False
        self.started_ms = utc_now_ms()
        self.last_frame_recv_ms: Optional[int] = None
        self.last_maintenance_monotonic = 0.0
        self.last_control_write_monotonic = 0.0
        self.deleted_partitions: List[str] = []
        self.compressed_partitions: List[str] = []
        self.status = "created"
        self.last_error: Optional[str] = None
        self.compression_warning: Optional[str] = None
        self.compression_task: Optional[asyncio.Task[List[str]]] = None
        self.next_compression_check_monotonic = 0.0

    def _append(self, stream: str, record: Mapping[str, Any]) -> None:
        self.store.append(stream, record)

    def _start_markers(self, *, reconnect: bool) -> None:
        now_ns = time.time_ns()
        now_ms = now_ns // 1_000_000
        for symbol in self.config.symbols:
            if "book" in self.config.streams:
                book_marker = self.trackers[symbol].on_connection_start(
                    connection_id=self.connection_id,
                    recv_ts_ms=now_ms,
                    recv_ts_ns=now_ns,
                    frame_seq=self.connection_frame_seq,
                )
                self._append("book", book_marker)
            if "trades" not in self.config.streams:
                continue
            if self.existing_tape[(symbol, "trades")] and not reconnect:
                self._append(
                    "trades",
                    marker_record(
                        stream="trades",
                        symbol=symbol,
                        kind="gap",
                        reason="collector_process_restart_unobserved_interval",
                        recv_ts_ms=now_ms,
                        recv_ts_ns=now_ns,
                        connection_id=self.connection_id,
                        frame_seq=self.connection_frame_seq,
                    ),
                )
            trade_kind = "stream_resume" if reconnect or self.existing_tape[(symbol, "trades")] else "stream_start"
            self._append(
                "trades",
                marker_record(
                    stream="trades",
                    symbol=symbol,
                    kind=trade_kind,
                    reason="websocket_subscription_sent",
                    recv_ts_ms=now_ms,
                    recv_ts_ns=now_ns,
                    connection_id=self.connection_id,
                    frame_seq=self.connection_frame_seq,
                ),
            )
        self.streams_started = True

    def _disconnect_markers(self, reason: str) -> None:
        if not self.streams_started:
            return
        now_ns = time.time_ns()
        now_ms = now_ns // 1_000_000
        for symbol in self.config.symbols:
            if "book" in self.config.streams:
                self._append(
                    "book",
                    self.trackers[symbol].on_disconnect(
                        reason=reason,
                        recv_ts_ms=now_ms,
                        recv_ts_ns=now_ns,
                        connection_id=self.connection_id,
                        frame_seq=self.connection_frame_seq,
                    ),
                )
            if "trades" in self.config.streams:
                self._append(
                    "trades",
                    marker_record(
                        stream="trades",
                        symbol=symbol,
                        kind="gap",
                        reason=reason,
                        recv_ts_ms=now_ms,
                        recv_ts_ns=now_ns,
                        connection_id=self.connection_id,
                        frame_seq=self.connection_frame_seq,
                    ),
                )
        self.streams_started = False

    def _stop_markers(self, reason: str) -> None:
        if not self.streams_started:
            return
        now_ns = time.time_ns()
        now_ms = now_ns // 1_000_000
        for symbol in self.config.symbols:
            for stream in self.config.streams:
                self._append(
                    stream,
                    marker_record(
                        stream=stream,
                        symbol=symbol,
                        kind="stream_stop",
                        reason=reason,
                        recv_ts_ms=now_ms,
                        recv_ts_ns=now_ns,
                        connection_id=self.connection_id,
                        frame_seq=self.connection_frame_seq,
                    ),
                )
        self.streams_started = False

    def _tracker_state(self) -> Dict[str, Any]:
        if "book" not in self.config.streams:
            return {}
        return {
            symbol: {
                "book_snapshot_synced": tracker.valid,
                "last_update_id": tracker.last_update_id,
                "last_seq": tracker.last_seq,
                "segment_id": tracker.current_segment_id,
            }
            for symbol, tracker in self.trackers.items()
        }

    def write_control(self, status: str, *, error: Optional[str] = None) -> None:
        now_ms = utc_now_ms()
        self.status = status
        self.last_error = error
        storage = storage_status(
            self.config.root,
            max_disk_bytes=self.config.max_disk_bytes,
            min_free_bytes=self.config.min_free_bytes,
        )
        partitions = self.store.stats_manifest(now_ms=now_ms)
        coverage_alerts = [
            {
                "path": path,
                "coverage": row.get("coverage"),
                "observed_window_ms": row.get("observed_window_ms"),
            }
            for path, row in partitions.items()
            if int(row.get("observed_window_ms") or 0) >= 60_000
            and float(row.get("coverage") or 0.0) < self.config.coverage_alert_below
        ]
        common = {
            "collector_id": self.collector_id,
            "generated_ts_ms": now_ms,
            "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000)),
            "status": status,
            "error": error,
            "public_only": True,
            "authentication": False,
            "order_capability": False,
            "started_ts_ms": self.started_ms,
            "connection_count": self.connection_count,
            "connection_id": self.connection_id or None,
            "last_frame_recv_ts_ms": self.last_frame_recv_ms,
            "last_frame_lag_ms": now_ms - self.last_frame_recv_ms if self.last_frame_recv_ms else None,
            "config_sha256": config_fingerprint(self.config.public_dict()),
            "storage": storage,
            "coverage_alert_below": self.config.coverage_alert_below,
            "coverage_alerts": coverage_alerts,
            "sequence_integrity_policy": {
                "raw_update_id_and_cross_seq_preserved": True,
                "numeric_step_of_one_required": False,
                "monotonic_within_snapshot_segment": True,
                "transport_disconnects_are_explicit_gaps": True,
                "fresh_snapshot_resets_segment": True,
            },
            "compression": {
                "enabled": self.config.compress_rotated,
                "background_task_running": bool(
                    self.compression_task is not None and not self.compression_task.done()
                ),
                "warning": self.compression_warning,
            },
            "trackers": self._tracker_state(),
        }
        manifest = {
            "schema": MANIFEST_SCHEMA,
            **common,
            "manifest_is_advisory": True,
            "validator_is_authoritative": True,
            "config": self.config.public_dict(),
            "session_partitions": partitions,
            "retention": {
                "days": self.config.retention_days,
                "mode": self.config.retention_mode,
                "deleted_this_process": list(self.deleted_partitions),
                "compressed_this_process": list(self.compressed_partitions),
            },
        }
        heartbeat = {
            "schema": HEARTBEAT_SCHEMA,
            **common,
            "partition_count_this_process": len(partitions),
        }
        atomic_write_json(self.config.root / "manifest.json", manifest)
        atomic_write_json(self.config.root / "heartbeat.json", heartbeat)
        self.last_control_write_monotonic = time.monotonic()

    def maintenance(self, *, force: bool = False) -> None:
        now_mono = time.monotonic()
        if not force and now_mono - self.last_maintenance_monotonic < self.config.maintenance_interval_sec:
            if now_mono - self.last_control_write_monotonic >= self.config.heartbeat_interval_sec:
                self.write_control(self.status, error=self.last_error)
            return
        now_ms = utc_now_ms()
        today = utc_day(now_ms)
        self.store.rotate_before_day(today)
        if self.compression_task is not None and self.compression_task.done():
            try:
                self.compressed_partitions.extend(self.compression_task.result())
                self.compression_warning = None
            except Exception as exc:
                self.compression_warning = f"background_compression_failed:{type(exc).__name__}:{exc}"
            self.compression_task = None
        if self.config.retention_mode == "delete" and self.compression_task is None:
            self.deleted_partitions.extend(
                prune_expired_partitions(
                    self.config.root,
                    now_ms=now_ms,
                    retention_days=self.config.retention_days,
                )
            )
        disk = enforce_storage_budget(
            self.config.root,
            max_disk_bytes=self.config.max_disk_bytes,
            min_free_bytes=self.config.min_free_bytes,
        )
        if (
            self.config.compress_rotated
            and self.compression_task is None
            and now_mono >= self.next_compression_check_monotonic
        ):
            candidates = completed_uncompressed_partitions(self.config.root, now_ms=now_ms)
            reserve = sum(path.stat().st_size for path in candidates)
            if candidates and int(disk["free_bytes"]) - reserve < self.config.min_free_bytes:
                self.compression_warning = (
                    f"compression_skipped_free_space_reserve:candidates={len(candidates)}:reserve_bytes={reserve}"
                )
            elif candidates:
                self.compression_warning = None
                self.compression_task = asyncio.create_task(
                    asyncio.to_thread(
                        compress_completed_partitions,
                        self.config.root,
                        now_ms=now_ms,
                        level=self.config.compression_level,
                    )
                )
            self.next_compression_check_monotonic = now_mono + 300.0
        self.last_maintenance_monotonic = now_mono
        self.write_control(self.status, error=self.last_error)

    def handle_message(self, message: Mapping[str, Any], *, recv_ts_ns: int) -> None:
        topic = str(message.get("topic") or "")
        recv_ts_ms = recv_ts_ns // 1_000_000
        if topic.startswith("orderbook."):
            if "book" not in self.config.streams:
                raise FrameContractError("received unsubscribed orderbook stream")
            record = normalize_book_frame(
                message,
                recv_ts_ms=recv_ts_ms,
                recv_ts_ns=recv_ts_ns,
                connection_id=self.connection_id,
                frame_seq=self.connection_frame_seq,
                depth=self.config.depth,
            )
            symbol = str(record["symbol"])
            if symbol not in self.trackers:
                raise FrameContractError(f"unsubscribed orderbook symbol: {symbol}")
            records, reconnect = self.trackers[symbol].process(record)
            for row in records:
                self._append("book", row)
            if reconnect:
                raise SequenceGapError(f"{symbol}: {records[0].get('reason')}")
            return
        if topic.startswith("publicTrade."):
            if "trades" not in self.config.streams:
                raise FrameContractError("received unsubscribed publicTrade stream")
            for row in normalize_trade_frame(
                message,
                recv_ts_ms=recv_ts_ms,
                recv_ts_ns=recv_ts_ns,
                connection_id=self.connection_id,
                frame_seq=self.connection_frame_seq,
            ):
                if row["symbol"] not in self.config.symbols:
                    raise FrameContractError(f"unsubscribed trade symbol: {row['symbol']}")
                self._append("trades", row)
            return
        if message.get("op") == "subscribe" and message.get("success") is False:
            raise FrameContractError(f"Bybit rejected subscription: {message.get('ret_msg') or message.get('retMsg')}")
        # subscribe acknowledgements and pong frames carry no market event.

    async def run(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets dependency is required")
        if self.config.compress_rotated and importlib.util.find_spec("zstandard") is None:
            raise RuntimeError("zstandard dependency is required with --compress-rotated")
        self.store.acquire()
        try:
            self.existing_tape = {
                (symbol, stream): self.store.has_existing_tape(symbol, stream)
                for symbol in self.config.symbols
                for stream in self.config.streams
            }
            self.trackers = (
                {
                    symbol: BookSequenceTracker(
                        symbol,
                        self.config.depth,
                        resuming_existing_tape=self.existing_tape[(symbol, "book")],
                    )
                    for symbol in self.config.symbols
                }
                if "book" in self.config.streams
                else {}
            )
            self.status = "starting"
            self.maintenance(force=True)
        except BaseException as exc:
            self.status = "blocked"
            self.last_error = str(exc)
            try:
                try:
                    self.write_control(self.status, error=self.last_error)
                except Exception:
                    pass
            finally:
                self.store.close()
            raise
        stop_at = time.monotonic() + self.config.duration_sec if self.config.duration_sec else None
        reconnect_delay = self.config.reconnect_initial_sec
        connected_once = False
        fatal: Optional[BaseException] = None
        try:
            while stop_at is None or time.monotonic() < stop_at:
                self.maintenance()
                self.connection_count += 1
                self.connection_id = f"{self.collector_id}-c{self.connection_count}-{uuid.uuid4().hex[:8]}"
                self.connection_frame_seq = 0
                connection_day = utc_day(utc_now_ms())
                try:
                    async with websockets.connect(
                        self.config.ws_url,
                        ping_interval=self.config.ping_interval_sec,
                        ping_timeout=self.config.ping_timeout_sec,
                        max_queue=self.config.max_queue,
                    ) as websocket:
                        topics = [
                            topic
                            for symbol in self.config.symbols
                            for topic in (
                                ([f"orderbook.{self.config.depth}.{symbol}"] if "book" in self.config.streams else [])
                                + ([f"publicTrade.{symbol}"] if "trades" in self.config.streams else [])
                            )
                        ]
                        for chunk in _chunks(topics, self.config.chunk_size):
                            await websocket.send(json.dumps({"op": "subscribe", "args": chunk}, separators=(",", ":")))
                            await asyncio.sleep(0.05)
                        self._start_markers(reconnect=connected_once)
                        connected_once = True
                        self.last_error = None
                        self.status = "connected_waiting_book_snapshots"
                        self.write_control(self.status)
                        last_wire_monotonic = time.monotonic()
                        reconnect_delay = self.config.reconnect_initial_sec
                        while stop_at is None or time.monotonic() < stop_at:
                            if utc_day(utc_now_ms()) != connection_day:
                                raise UtcRotationReconnect("utc_partition_rotation")
                            remaining_idle = self.config.idle_timeout_sec - (time.monotonic() - last_wire_monotonic)
                            if remaining_idle <= 0:
                                raise asyncio.TimeoutError("public websocket idle timeout")
                            timeout = min(self.config.heartbeat_interval_sec, remaining_idle)
                            if stop_at is not None:
                                timeout = min(timeout, max(0.01, stop_at - time.monotonic()))
                            try:
                                raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                            except asyncio.TimeoutError:
                                self.maintenance()
                                continue
                            recv_ns = time.time_ns()
                            recv_ms = recv_ns // 1_000_000
                            if utc_day(recv_ms) != connection_day:
                                raise UtcRotationReconnect("utc_partition_rotation")
                            last_wire_monotonic = time.monotonic()
                            self.last_frame_recv_ms = recv_ms
                            self.connection_frame_seq += 1
                            try:
                                message = json.loads(raw)
                            except (json.JSONDecodeError, TypeError) as exc:
                                raise FrameContractError("malformed websocket JSON frame") from exc
                            if not isinstance(message, Mapping):
                                raise FrameContractError("websocket frame must be a JSON object")
                            self.handle_message(message, recv_ts_ns=recv_ns)
                            if "book" not in self.config.streams or all(tracker.valid for tracker in self.trackers.values()):
                                self.status = "collecting"
                            self.maintenance()
                except asyncio.CancelledError:
                    raise
                except StorageLimitExceeded:
                    raise
                except Exception as exc:
                    reason = "utc_rotation_reconnect" if isinstance(exc, UtcRotationReconnect) else f"websocket_disconnect:{type(exc).__name__}"
                    self._disconnect_markers(reason)
                    self.status = "reconnecting"
                    self.write_control(self.status, error=str(exc))
                    if stop_at is not None and time.monotonic() >= stop_at:
                        break
                    await asyncio.sleep(reconnect_delay + random.uniform(0, min(1.0, reconnect_delay * 0.2)))
                    reconnect_delay = min(self.config.reconnect_max_sec, reconnect_delay * 1.7)
            self._stop_markers("duration_complete")
            self.status = "stopped_cleanly"
        except asyncio.CancelledError as exc:
            self._stop_markers("cancelled_cleanly")
            self.status = "stopped_cleanly"
            fatal = exc
        except BaseException as exc:
            try:
                self._disconnect_markers(f"fatal:{type(exc).__name__}")
            except BaseException:
                pass
            self.status = "blocked"
            self.last_error = str(exc)
            fatal = exc
        finally:
            try:
                if self.compression_task is not None:
                    try:
                        self.compressed_partitions.extend(await self.compression_task)
                        self.compression_warning = None
                    except Exception as exc:
                        self.compression_warning = (
                            f"background_compression_failed:{type(exc).__name__}:{exc}"
                        )
                    self.compression_task = None
                self.store.flush()
                self.write_control(self.status, error=self.last_error)
            finally:
                self.store.close()
        if fatal is not None:
            raise fatal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Public-only replayable Bybit L2/publicTrade collector",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--max-symbols", type=int, default=20)
    parser.add_argument(
        "--streams",
        default="book,trades",
        help="book,trades together, or book/trades independently",
    )
    parser.add_argument(
        "--max-book-symbols",
        type=int,
        default=2,
        help="fail-closed L2 fanout cap; publicTrade-only can use --max-symbols",
    )
    parser.add_argument("--depth", type=int, choices=SUPPORTED_DEPTHS, default=200)
    parser.add_argument("--ws-url", default=DEFAULT_WS_URL)
    parser.add_argument("--root", default="runtime/tape")
    parser.add_argument("--duration-sec", type=float, default=0.0, help="0 runs until stopped")
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--ping-interval-sec", type=float, default=20.0)
    parser.add_argument("--ping-timeout-sec", type=float, default=20.0)
    parser.add_argument("--idle-timeout-sec", type=float, default=90.0)
    parser.add_argument("--reconnect-initial-sec", type=float, default=2.0)
    parser.add_argument("--reconnect-max-sec", type=float, default=60.0)
    parser.add_argument("--heartbeat-interval-sec", type=float, default=15.0)
    parser.add_argument("--maintenance-interval-sec", type=float, default=15.0)
    parser.add_argument("--fsync-every-records", type=int, default=2000)
    parser.add_argument("--fsync-interval-sec", type=float, default=1.0)
    parser.add_argument("--max-queue", type=int, default=4096)
    parser.add_argument("--max-disk-gb", type=float, default=4.0)
    parser.add_argument("--min-free-gb", type=float, default=4.0)
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument(
        "--retention-mode",
        choices=("stop", "delete"),
        default="stop",
        help="stop preserves old data; delete prunes only recognized expired tape partitions",
    )
    parser.add_argument("--compress-rotated", action="store_true", help="zstd-compress verified completed UTC partitions")
    parser.add_argument("--compression-level", type=int, default=6)
    parser.add_argument("--coverage-alert-below", type=float, default=0.98)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="validate config/dependencies/disk and exit without network or writes",
    )
    return parser


async def run_with_signal_shutdown(runtime: CollectorRuntime) -> None:
    """Translate SIGINT/SIGTERM into cancellation so stop markers are durable."""
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(runtime.run())
    installed: List[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, task.cancel)
            installed.append(sig)
        except (NotImplementedError, RuntimeError):  # pragma: no cover - non-POSIX loop
            pass
    try:
        await task
    except asyncio.CancelledError:
        # CollectorRuntime already fsynced data and persisted clean stop markers.
        return
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config = config_from_args(args)
        if args.preflight:
            receipt = preflight(config)
            print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
            return 0 if receipt["ok"] else 2
        asyncio.run(run_with_signal_shutdown(CollectorRuntime(config)))
        return 0
    except KeyboardInterrupt:
        return 130
    except (TapeError, ValueError, RuntimeError) as exc:
        print(f"collector blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
