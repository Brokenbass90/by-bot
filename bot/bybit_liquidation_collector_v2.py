"""Durable public-source journal. No clients, keys, signals, judges or orders.

One raw frame and its normalized items share one fsynced, hash-chained record.
Exchange events have no unique ID/sequence: duplicate candidates are retained;
quiet periods and connected transport never imply complete event coverage.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from bot.bybit_liquidation_source_v2 import SCHEMA, OFFICIAL_SOURCE, normalize_liquidation

ENDPOINT = "wss://stream.bybit.com/v5/public/linear"
GENESIS = "0" * 64
MAX_WIRE_BYTES = 1024 * 1024
MIN_TIMESTAMP_MS = 946684800000


class CaptureStopped(RuntimeError):
    """Fail closed; storage/identity failures must not become restart loops."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value, field):
    return sha(canonical({k: v for k, v in value.items() if k != field}))


def safe_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CaptureStopped("OUTPUT_SYMLINK")
    return path


def atomic(path, value):
    path = safe_path(path)
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except OSError as exc:
        raise CaptureStopped("HEARTBEAT_DURABILITY_FAILURE") from exc
    finally:
        if temporary.exists(): temporary.unlink()


class Journal:
    def __init__(self, root, symbols, source_files, *, now_ms=None,
                 min_free_bytes=1024**3, max_capture_bytes=4 * 1024**3):
        self.lock_fd = self.file = None
        self.root = safe_path(root)
        symbols = tuple(symbols)
        if (not symbols or len(set(symbols)) != len(symbols)
                or any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9]{2,30}USDT", s) for s in symbols)
                or not source_files or any(not re.fullmatch(r"[a-f0-9]{64}", v) for v in source_files.values())
                or type(min_free_bytes) is not int or min_free_bytes < 0
                or type(max_capture_bytes) is not int or max_capture_bytes <= 0):
            raise CaptureStopped("INVALID_SOURCE_CONFIGURATION")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.lock_fd = os.open(safe_path(self.root / "writer.lock"),
                                   os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try: fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise CaptureStopped("ALREADY_RUNNING")
            t = time.time_ns() // 1000000 if now_ms is None else now_ms
            self.symbols = symbols
            self.spec = dict(schema="BYBIT_LIQUIDATION_CAPTURE_MANIFEST_V2",
                             normalized_schema=SCHEMA, endpoint=ENDPOINT,
                             official_protocol=OFFICIAL_SOURCE, symbols=list(symbols),
                             source_files=source_files, min_free_bytes=min_free_bytes,
                             max_capture_bytes=max_capture_bytes, orders_allowed=False,
                             private_api_allowed=False, strategy_authority=False,
                             side_semantics="Buy=liquidated_long;Sell=liquidated_short",
                             price_basis="bankruptcy_not_execution_price",
                             duplicate_policy="flag_candidates_retain_all_no_unique_exchange_id",
                             full_exchange_coverage="UNKNOWN_NO_SEQUENCE_OR_BACKFILL")
            path = self.root / "source-manifest.json"
            if path.exists():
                self.manifest = json.loads(safe_path(path).read_bytes())
                if digest(self.manifest, "manifest_sha256") != self.manifest.get("manifest_sha256"):
                    raise CaptureStopped("MANIFEST_HASH_INVALID")
                if {k: self.manifest.get(k) for k in self.spec} != self.spec:
                    raise CaptureStopped("MANIFEST_DRIFT")
            else:
                if (self.root / "runs").exists(): raise CaptureStopped("MANIFEST_MISSING_WITH_CAPTURE")
                self.manifest = dict(self.spec, epoch_id=uuid.uuid4().hex, created_ms=t)
                self.manifest["manifest_sha256"] = digest(self.manifest, "manifest_sha256")
                atomic(path, self.manifest)
            if t < self.manifest["created_ms"]: raise CaptureStopped("CLOCK_REGRESSION")
            self.counts = Counter(); self.qa_counts = Counter(); self.symbol_counts = Counter()
            self.recent = OrderedDict(); self.last_event_by_symbol = {}
            self.capture_bytes = 0; self.last_event_ms = None
            self.connected_at_ms = self.last_receive_ms = self.last_pong_ms = None
            self.connection_id = self.request_id = None
            self.subscription_confirmed = self.subscription_rejected = False
            self.disconnected_at_ms = None
            self.status = "STARTING"; self.sequence = 0; self.tip = GENESIS
            runs = safe_path(self.root / "runs"); runs.mkdir(exist_ok=True, mode=0o700)
            old_runs = sorted(runs.iterdir())
            for old in old_runs:
                if old.is_symlink() or not old.is_dir(): raise CaptureStopped("CAPTURE_PATH_INVALID")
                previous = GENESIS
                capture = safe_path(old / "frames.jsonl")
                if not capture.is_file(): raise CaptureStopped("CAPTURE_MISSING")
                with capture.open("rb") as stream:
                    for line in stream:
                        if len(line) > MAX_WIRE_BYTES * 3 or not line.endswith(b"\n"):
                            raise CaptureStopped("CAPTURE_PARTIAL_OR_OVERSIZED_RECORD")
                        row = json.loads(line)
                        if (row.get("prev_sha256") != previous
                                or digest(row, "record_sha256") != row.get("record_sha256")
                                or row.get("source_manifest_sha256") != self.manifest["manifest_sha256"]):
                            raise CaptureStopped("CAPTURE_INTEGRITY_INVALID")
                        previous = row["record_sha256"]; self._account(row)
                        self.capture_bytes += len(line)
            self.run_id = str(t) + "-" + uuid.uuid4().hex
            directory = safe_path(runs / self.run_id); directory.mkdir(mode=0o700)
            fd = os.open(directory / "frames.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self.file = os.fdopen(fd, "wb", buffering=0)
            for parent in (directory, runs):
                directory_fd = os.open(parent, os.O_RDONLY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
            self._append(dict(kind="PROCESS_START", receive_ms=t, normalized_events=[],
                              qa_flags=[], previous_run_count=len(old_runs)))
            if old_runs:
                self._append(dict(kind="PROCESS_RESTART_GAP", receive_ms=t,
                                  missing_event_count=None, full_coverage="UNKNOWN",
                                  normalized_events=[], qa_flags=["PROCESS_RESTART_UNOBSERVED_INTERVAL"]))
            self.heartbeat(t)
        except Exception:
            self.close(); raise

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def check_storage(self, extra=0):
        if self.capture_bytes + extra > self.spec["max_capture_bytes"]:
            raise CaptureStopped("STOP_STORAGE_CAP")
        if shutil.disk_usage(self.root).free < self.spec["min_free_bytes"]:
            raise CaptureStopped("STOP_FREE_SPACE")

    def _remember(self, key):
        self.recent[key] = None; self.recent.move_to_end(key)
        if len(self.recent) > 50000: self.recent.popitem(last=False)

    def _account(self, row):
        self.counts[row["kind"]] += 1
        self.qa_counts.update(row.get("qa_flags", []))
        for event in row.get("normalized_events", []):
            self.counts["EVENT"] += 1; self.symbol_counts[event["symbol"]] += 1
            self.qa_counts.update(event.get("qa_flags", []))
            self._remember(event["raw_item_canonical_sha256"])
            self.last_event_ms = max(self.last_event_ms or 0, event["ts_ms"])
            self.last_event_by_symbol[event["symbol"]] = max(
                self.last_event_by_symbol.get(event["symbol"], 0), event["ts_ms"])

    def _append(self, value):
        row = dict(value, capture_run_id=self.run_id, capture_sequence=self.sequence + 1,
                   source_manifest_sha256=self.manifest["manifest_sha256"], prev_sha256=self.tip)
        row["record_sha256"] = digest(row, "record_sha256")
        encoded = canonical(row) + b"\n"; self.check_storage(len(encoded))
        remaining = memoryview(encoded)
        try:
            while remaining:
                written = self.file.write(remaining)
                if not written: raise CaptureStopped("CAPTURE_WRITE_INCOMPLETE")
                remaining = remaining[written:]
            os.fsync(self.file.fileno())
        except OSError as exc:
            raise CaptureStopped("CAPTURE_DURABILITY_FAILURE") from exc
        self.sequence += 1; self.tip = row["record_sha256"]; self.capture_bytes += len(encoded)
        self._account(row)
        return row

    def connected(self, connection_id, request_id, now_ms):
        if self.disconnected_at_ms is not None:
            self._append(dict(kind="OBSERVATION_GAP", start_ms=self.disconnected_at_ms,
                              end_ms=now_ms, receive_ms=now_ms, missing_event_count=None,
                              normalized_events=[], qa_flags=["DISCONNECT_UNOBSERVED_INTERVAL"]))
        self.disconnected_at_ms = None; self.connection_id = connection_id
        self.request_id = request_id; self.connected_at_ms = now_ms
        self.last_receive_ms = self.last_pong_ms = None
        self.subscription_confirmed = self.subscription_rejected = False
        self.status = "SUBSCRIBING"
        self._append(dict(kind="CONNECTED", receive_ms=now_ms, connection_id=connection_id,
                          normalized_events=[], qa_flags=[]))

    def disconnected(self, reason, now_ms):
        self.status = "DISCONNECTED"; self.subscription_confirmed = False
        self.disconnected_at_ms = now_ms
        self._append(dict(kind="DISCONNECTED", receive_ms=now_ms,
                          connection_id=self.connection_id, reason=str(reason)[:200],
                          normalized_events=[], qa_flags=["TRANSPORT_DISCONNECT"]))

    def receive(self, payload, *, recv_ms, connection_id):
        wire = payload.encode() if isinstance(payload, str) else bytes(payload)
        if len(wire) > MAX_WIRE_BYTES: raise CaptureStopped("WIRE_SIZE_LIMIT")
        flags = []; events = []; message = None; raw_text = None
        try:
            raw_text = wire.decode("utf-8"); message = json.loads(raw_text)
        except UnicodeDecodeError: flags.append("INVALID_UTF8")
        except (ValueError, RecursionError): flags.append("MALFORMED_JSON")
        if connection_id != self.connection_id:
            flags.append("STALE_CONNECTION_FRAME"); message = None
        if message is not None:
            if not isinstance(message, dict): flags.append("FRAME_SCHEMA_INVALID")
            elif message.get("op") == "subscribe":
                if message.get("req_id") == self.request_id:
                    if message.get("success") is True: self.subscription_confirmed = True
                    else:
                        self.subscription_rejected = True
                        flags.append("SUBSCRIPTION_REJECTED")
                else: flags.append("SUBSCRIPTION_ACK_UNMATCHED")
            elif (message.get("op") == "pong"
                  or (message.get("op") == "ping" and message.get("ret_msg") == "pong"
                      and message.get("success") is True)):
                self.last_pong_ms = recv_ms
            elif not str(message.get("topic", "")).startswith("allLiquidation."):
                flags.append("UNEXPECTED_TOPIC")
            else:
                symbol = message["topic"].removeprefix("allLiquidation.")
                frame_time = message.get("ts")
                if symbol not in self.symbols: flags.append("UNREQUESTED_SYMBOL")
                elif (message.get("type") != "snapshot" or not isinstance(message.get("data"), list)
                      or type(frame_time) is not int or not MIN_TIMESTAMP_MS <= frame_time <= recv_ms + 60000):
                    flags.append("FRAME_SCHEMA_INVALID")
                else:
                    batch_keys = set()
                    batch_times = dict(self.last_event_by_symbol)
                    if frame_time > recv_ms: flags.append("FRAME_AFTER_RECEIVE_CLOCK_SKEW")
                    for index, item in enumerate(message["data"]):
                        e = normalize_liquidation(item, topic_symbol=symbol, recv_ts_ms=recv_ms)
                        if e is None: flags.append("EVENT_SCHEMA_INVALID"); continue
                        if not MIN_TIMESTAMP_MS <= e["ts_ms"] <= recv_ms + 60000:
                            flags.append("EVENT_TIMESTAMP_INVALID"); continue
                        qa = []
                        key = e["raw_item_canonical_sha256"]
                        if key in self.recent or key in batch_keys: qa.append("DUPLICATE_CANDIDATE_RETAINED")
                        if e["ts_ms"] < batch_times.get(symbol, 0):
                            qa.append("EVENT_TIME_REGRESSION_RETAINED")
                        if e["ts_ms"] > recv_ms: qa.append("EVENT_AFTER_RECEIVE_CLOCK_SKEW")
                        if not self.subscription_confirmed: qa.append("SUBSCRIPTION_UNCONFIRMED_RETAINED")
                        batch_keys.add(key)
                        batch_times[symbol] = max(batch_times.get(symbol, 0), e["ts_ms"])
                        e.update(t_available_ms=recv_ms, frame_ts_ms=frame_time,
                                 causal_clock_status=("UNKNOWN" if e["ts_ms"] > recv_ms or frame_time > recv_ms else "RECEIVE_OBSERVED"),
                                 source_manifest_sha256=self.manifest["manifest_sha256"],
                                 raw_payload_sha256=sha(wire), raw_item_index=index,
                                 capture_event_id=f"{self.run_id}:{self.sequence + 1}:{index}", qa_flags=qa)
                        events.append(e)
        self._append(dict(kind="FRAME", receive_ms=recv_ms, connection_id=connection_id,
                          receive_monotonic_ns=time.monotonic_ns(), raw_payload_sha256=sha(wire),
                          raw_text=raw_text, raw_base64=(base64.b64encode(wire).decode() if raw_text is None else None),
                          normalized_events=events, qa_flags=flags))
        if connection_id == self.connection_id: self.last_receive_ms = recv_ms
        return events

    def health(self, now_ms):
        status = self.status
        if self.subscription_confirmed:
            status = ("CONNECTED_OBSERVING" if self.last_event_ms is not None
                      and now_ms - self.last_event_ms < 60000 else "CONNECTED_QUIET")
        return dict(schema="BYBIT_LIQUIDATION_COLLECTOR_HEALTH_V2", as_of_ms=now_ms,
                    pid=os.getpid(), epoch_id=self.manifest["epoch_id"], capture_run_id=self.run_id,
                    source_manifest_sha256=self.manifest["manifest_sha256"], status=status,
                    subscription_confirmed=self.subscription_confirmed, symbols=list(self.symbols),
                    observed_event_count=self.counts["EVENT"], unique_exchange_event_count=None,
                    frame_count=self.counts["FRAME"], symbol_event_counts=dict(self.symbol_counts),
                    counts=dict(self.counts), qa_counts=dict(self.qa_counts),
                    restart_gap_count=self.counts["PROCESS_RESTART_GAP"],
                    transport_gap_count=self.counts["OBSERVATION_GAP"],
                    last_receive_ms=self.last_receive_ms, last_pong_ms=self.last_pong_ms,
                    last_event_ms=self.last_event_ms, capture_bytes=self.capture_bytes,
                    disk_free_bytes=shutil.disk_usage(self.root).free,
                    qa_status="WARN" if self.qa_counts else "OBSERVATIONAL_PASS",
                    full_exchange_coverage="UNKNOWN_NO_SEQUENCE_OR_BACKFILL",
                    capture_tip_sha256=self.tip, orders_allowed=False,
                    private_api_allowed=False, strategy_authority=False)

    def heartbeat(self, now_ms, status=None):
        result = self.health(now_ms)
        if status is not None: result["status"] = status
        result["heartbeat_sha256"] = digest(result, "heartbeat_sha256")
        atomic(self.root / "heartbeat.json", result)
        return result

    def close(self):
        if self.file is not None: self.file.close(); self.file = None
        if self.lock_fd is not None: os.close(self.lock_fd); self.lock_fd = None
