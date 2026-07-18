#!/usr/bin/env python3
"""Run the bounded public-only event-universe research station.

Default invocation is a no-network/no-write preflight.  Collection requires
explicit public-network and research-only acknowledgements.  The module has no
credential, private API, broker, order, transfer, withdrawal, risk or live
router integration.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.event_universe_v1 import (  # noqa: E402
    CONFIG_SCHEMA_ID,
    SNAPSHOT_SCHEMA_ID,
    SOURCE_ID,
    EventScoreV1,
    EventUniverseConfigV1,
    EventUniverseError,
    MarketEligibilityV1,
    build_snapshot_payload,
    canonical_bytes,
    closed_contiguous_m5,
    evaluate_market_eligibility,
    score_event_m5,
    select_prefetch_symbols,
    sha256_payload,
    validate_snapshot_payload,
)


DEFAULT_SPEC = ROOT / "configs/preregistered/event_universe_v1_20260718.json"
DEFAULT_RUN_ROOT = ROOT / "runtime/research/event_universe_v1_20260718"
PUBLIC_HOST = "api.bybit.com"
PUBLIC_PATHS = (
    "/v5/market/instruments-info",
    "/v5/market/tickers",
    "/v5/market/kline",
)
PUBLIC_QUERY_KEYS = {
    "/v5/market/instruments-info": {"category", "status", "limit", "cursor"},
    "/v5/market/tickers": {"category"},
    "/v5/market/kline": {"category", "symbol", "interval", "end", "limit"},
}
SPEC_SCHEMA_ID = "event_universe_preregistered_spec_v1"
LATEST_SCHEMA_ID = "event_universe_latest_state_v1"
LAUNCH_SCHEMA_ID = "event_universe_launch_receipt_v1"
REPLAY_SCHEMA_ID = "event_universe_normalized_replay_v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
IMPLEMENTATION_RELATIVE_PATHS = (
    "bot/event_universe_v1.py",
    "scripts/run_event_universe_v1.py",
    "scripts/supervise_event_universe_v1.sh",
    "scripts/launch_event_universe_v1.sh",
)
ChainState = tuple[int, Path | None, dict[str, Any] | None, dict[str, list[list[Any]]]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Fail closed instead of following a response away from the frozen host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _exact_int(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise EventUniverseError(f"{label} must be an exact integer")
    try:
        result = int(value)
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise EventUniverseError(f"{label} must be an exact integer") from exc
    if numeric != float(result) or (positive and result <= 0):
        raise EventUniverseError(f"{label} must be an exact integer")
    return result


def _load_spec(path: Path) -> tuple[dict[str, Any], EventUniverseConfigV1]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != SPEC_SCHEMA_ID or payload.get("strategy_id") != "event_universe_v1":
        raise EventUniverseError("event-universe spec identity mismatch")
    if payload.get("source_id") != SOURCE_ID or payload.get("status") != "RESEARCH_ONLY_DEFAULT_DISABLED":
        raise EventUniverseError("event-universe source/status mismatch")
    authority = payload.get("authority")
    required_authority = {
        "research_only": True,
        "executable": False,
        "private_api_calls": False,
        "api_keys_or_environment_reads": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "risk_or_live_router_mutation": False,
        "performance_claims": False,
        "promotion_authority": False,
    }
    if authority != required_authority:
        raise EventUniverseError("event-universe authority is not frozen fail-closed")
    required_analysis_policy = {
        "thresholds_and_universe_rules_locked_for_this_run": True,
        "no_midrun_outcome_tuning": True,
        "candidate_labels_are_advisory_not_trade_signals": True,
        "this_discovery_run_cannot_authorize_promotion": True,
        "downstream_long_and_short_consumers_require_separate_preregistration_and_sealed_tests": True,
    }
    if payload.get("analysis_policy") != required_analysis_policy:
        raise EventUniverseError("event-universe prospective analysis policy mismatch")
    config_payload = payload.get("config")
    if not isinstance(config_payload, Mapping):
        raise EventUniverseError("event-universe config is missing")
    config = EventUniverseConfigV1(**dict(config_payload))
    public_io = payload.get("public_io")
    if not isinstance(public_io, Mapping):
        raise EventUniverseError("public I/O contract is missing")
    if public_io.get("host") != PUBLIC_HOST or tuple(public_io.get("paths") or ()) != PUBLIC_PATHS:
        raise EventUniverseError("public I/O host/path contract mismatch")
    frozen_public_identity = {
        "method": "GET_ONLY",
        "category": "linear",
        "instrument_status": "Trading",
        "instrument_contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "instrument_page_limit": 1000,
    }
    if any(public_io.get(key) != value for key, value in frozen_public_identity.items()):
        raise EventUniverseError("public I/O identity/filter contract mismatch")
    required_public_fields = {
        "host",
        "method",
        "paths",
        "category",
        "instrument_status",
        "instrument_contract_type",
        "quote_coin",
        "settle_coin",
        "instrument_page_limit",
        "kline_limit",
        "timeout_seconds",
        "max_retries",
        "backoff_base_seconds",
    }
    if set(public_io) != required_public_fields:
        raise EventUniverseError("public I/O fields are not exactly frozen")
    return payload, config


def _implementation_sha256_by_path() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in IMPLEMENTATION_RELATIVE_PATHS:
        path = ROOT / relative
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class PublicBybitEventClientV1:
    """Narrow public GET-only client with conservative retry/rate bounds."""

    def __init__(
        self,
        *,
        config: EventUniverseConfigV1,
        timeout_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        urlopen: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = _exact_int(max_retries, "max retries", positive=True)
        self.backoff_base_seconds = float(backoff_base_seconds)
        if not 0 < self.timeout_seconds <= 60 or not 0 < self.backoff_base_seconds <= 30:
            raise EventUniverseError("HTTP timeout/backoff is outside the frozen bound")
        if self.max_retries > 4:
            raise EventUniverseError("HTTP retry count exceeds the frozen cap")
        if urlopen is None:
            # An explicit empty proxy map prevents urllib from consulting proxy
            # environment variables.  Redirects are rejected by _NoRedirect.
            self._urlopen = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                _NoRedirect(),
            ).open
        else:
            self._urlopen = urlopen
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._last_request_at: float | None = None
        self._cycle_deadline: float | None = None

    def start_cycle(self) -> None:
        self._cycle_deadline = self._monotonic() + self.config.max_cycle_seconds

    def _remaining_cycle_seconds(self) -> float:
        if self._cycle_deadline is None:
            self.start_cycle()
        assert self._cycle_deadline is not None
        remaining = self._cycle_deadline - self._monotonic()
        if remaining <= 0:
            raise EventUniverseError("public collection exceeded the frozen cycle wall-clock cap")
        return remaining

    def _bounded_sleep(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        if seconds >= self._remaining_cycle_seconds():
            raise EventUniverseError("public retry/rate wait would exceed the frozen cycle cap")
        self._sleep(seconds)
        self._remaining_cycle_seconds()

    def validate_source_time(self, source_time_ms: int) -> None:
        source_time_ms = _exact_int(source_time_ms, "source server time", positive=True)
        local_time_ms = int(self._wall_time() * 1000)
        if abs(local_time_ms - source_time_ms) > self.config.max_source_time_skew_ms:
            raise EventUniverseError("public source/local timestamp skew exceeds the frozen cap")

    def _pace(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = (1.0 / self.config.public_requests_per_second) - (now - self._last_request_at)
            if wait > 0:
                self._bounded_sleep(wait)
        self._last_request_at = self._monotonic()

    @staticmethod
    def _url(path: str, params: Mapping[str, Any]) -> str:
        if path not in PUBLIC_PATHS:
            raise EventUniverseError("public path is not allowlisted")
        if set(params) - PUBLIC_QUERY_KEYS[path]:
            raise EventUniverseError("public query contains an unknown key")
        query = urllib.parse.urlencode([(key, str(value)) for key, value in params.items()])
        return f"https://{PUBLIC_HOST}{path}?{query}"

    def get_json(self, path: str, params: Mapping[str, Any]) -> dict[str, Any]:
        url = self._url(path, params)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if self._remaining_cycle_seconds() <= self.timeout_seconds:
                raise EventUniverseError("insufficient cycle budget for another public request")
            self._pace()
            request = urllib.request.Request(
                url,
                method="GET",
                headers={"User-Agent": "by-bot-event-universe-v1/1.0"},
            )
            try:
                with self._urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read(self.config.max_response_bytes + 1)
                self._remaining_cycle_seconds()
                if len(raw) > self.config.max_response_bytes:
                    raise EventUniverseError("public response exceeds frozen byte cap")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise EventUniverseError("public response root must be an object")
                code = payload.get("retCode")
                if code == 0:
                    return payload
                if code == 10006:
                    raise urllib.error.HTTPError(url, 429, "Bybit rate limit", {}, None)
                raise EventUniverseError(f"Bybit public API error {code}: {payload.get('retMsg')}")
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    raise EventUniverseError("Bybit public HTTP 403: station hard stop") from exc
                if exc.code != 429:
                    raise EventUniverseError(f"Bybit public HTTP {exc.code}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise EventUniverseError("public response is not valid UTF-8 JSON") from exc
            if attempt < self.max_retries:
                self._bounded_sleep(min(30.0, self.backoff_base_seconds * (2**attempt)))
        raise EventUniverseError(f"public request retries exhausted: {last_error}")

    def fetch_instruments(self) -> tuple[list[dict[str, Any]], list[str], int]:
        items: list[dict[str, Any]] = []
        hashes: list[str] = []
        cursor = ""
        seen_cursors: set[str] = set()
        server_times: list[int] = []
        for _ in range(10):
            params: dict[str, Any] = {"category": "linear", "status": "Trading", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            payload = self.get_json("/v5/market/instruments-info", params)
            hashes.append(sha256_payload(payload))
            server_time = _exact_int(payload.get("time"), "instrument response time", positive=True)
            self.validate_source_time(server_time)
            server_times.append(server_time)
            result = payload.get("result")
            if not isinstance(result, Mapping) or not isinstance(result.get("list"), list):
                raise EventUniverseError("instrument page result/list is missing")
            page = result["list"]
            if any(not isinstance(item, dict) for item in page):
                raise EventUniverseError("instrument page contains a non-object")
            items.extend(page)
            next_cursor = str(result.get("nextPageCursor") or "")
            if not next_cursor:
                break
            if next_cursor == cursor or next_cursor in seen_cursors:
                raise EventUniverseError("instrument pagination cursor repeated")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise EventUniverseError("instrument pagination exceeded frozen page cap")
        symbols = [str(item.get("symbol") or "").upper() for item in items]
        if len(set(symbols)) != len(symbols):
            raise EventUniverseError("instrument pagination returned duplicate symbols")
        return items, hashes, max(server_times)

    def fetch_tickers(self) -> tuple[list[dict[str, Any]], str, int]:
        payload = self.get_json("/v5/market/tickers", {"category": "linear"})
        result = payload.get("result")
        if not isinstance(result, Mapping) or not isinstance(result.get("list"), list):
            raise EventUniverseError("ticker result/list is missing")
        items = result["list"]
        if any(not isinstance(item, dict) for item in items):
            raise EventUniverseError("ticker list contains a non-object")
        symbols = [str(item.get("symbol") or "").upper() for item in items]
        if len(set(symbols)) != len(symbols):
            raise EventUniverseError("ticker response contains duplicate symbols")
        server_time = _exact_int(payload.get("time"), "ticker response time", positive=True)
        self.validate_source_time(server_time)
        return items, sha256_payload(payload), server_time

    def fetch_m5(self, symbol: str, *, as_of_ms: int, limit: int) -> tuple[list[list[Any]], str]:
        payload = self.get_json(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "5",
                "end": int(as_of_ms),
                "limit": int(limit),
            },
        )
        result = payload.get("result")
        if not isinstance(result, Mapping) or str(result.get("symbol") or "").upper() != symbol:
            raise EventUniverseError("kline result symbol mismatch")
        rows = result.get("list")
        if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
            raise EventUniverseError("kline list is missing or malformed")
        self.validate_source_time(_exact_int(payload.get("time"), "kline response time", positive=True))
        return rows, sha256_payload(payload)


def _assert_no_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if current.exists() and stat.S_ISLNK(os.lstat(current).st_mode):
            raise EventUniverseError("research path contains a symlink component")


def _research_root(path: Path, *, create: bool = True) -> Path:
    base = (ROOT / "runtime/research").resolve()
    # abspath performs lexical normalization, including '..', without allowing
    # an existing symlink to conceal the originally requested containment.
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise EventUniverseError("run root must stay below runtime/research") from exc
    _assert_no_symlink_components(target)
    if create:
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        _assert_no_symlink_components(target)
        os.chmod(target, 0o700)
    return target


def _atomic_write(path: Path, data: bytes, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_components(path.parent)
    if path.exists() and stat.S_ISLNK(os.lstat(path).st_mode):
        raise EventUniverseError("refusing symlink persistence target")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short atomic write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        if not replace and path.exists():
            raise EventUniverseError("immutable snapshot path already exists")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextlib.contextmanager
def _single_writer_lock(root: Path):
    """Hold one non-blocking process lock for every mutating station command."""
    root = _research_root(root)
    path = root / "station.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EventUniverseError("another event-universe writer owns this run root") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _read_json_regular(path: Path, *, max_bytes: int = 32 * 1024 * 1024) -> dict[str, Any]:
    raw = _read_regular_bytes(path, max_bytes=max_bytes)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise EventUniverseError("persisted event-universe JSON root must be an object")
    return payload


def _read_regular_bytes(path: Path, *, max_bytes: int) -> bytes:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise EventUniverseError("persisted event-universe path is unsafe")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise EventUniverseError("persisted event-universe file mode must be 0600")
    if info.st_size > max_bytes:
        raise EventUniverseError("persisted event-universe file exceeds byte cap")
    return path.read_bytes()


def _read_snapshot_regular(path: Path, *, config: EventUniverseConfigV1) -> dict[str, Any]:
    compressed = _read_regular_bytes(path, max_bytes=config.max_response_bytes)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as archive:
        raw = archive.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise EventUniverseError("persisted snapshot decompression cap exceeded")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventUniverseError("persisted snapshot is not valid gzip UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise EventUniverseError("persisted snapshot root must be an object")
    return payload


def _bind_normalized_replay(
    payload: Mapping[str, Any],
    normalized_m5_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
    *,
    previous_normalized_m5_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
    config: EventUniverseConfigV1,
) -> tuple[dict[str, Any], bytes]:
    score_symbols = [str(score["symbol"]) for score in payload["scores"]]
    normalized = {
        str(symbol): [list(row) for row in rows]
        for symbol, rows in sorted(normalized_m5_by_symbol.items())
    }
    if set(normalized) != set(score_symbols):
        raise EventUniverseError("normalized replay coverage must equal scored symbols")
    replay_by_symbol: dict[str, dict[str, Any]] = {}
    for symbol, current_rows in normalized.items():
        previous_rows = [list(row) for row in previous_normalized_m5_by_symbol.get(symbol, ())]
        use_delta = False
        appended_rows: list[list[Any]] = []
        if previous_rows:
            previous_last_start = int(previous_rows[-1][0])
            appended_rows = [row for row in current_rows if int(row[0]) > previous_last_start]
            reconstructed = (previous_rows + appended_rows)[-config.required_closed_bars :]
            use_delta = reconstructed == current_rows
        if use_delta:
            replay_by_symbol[symbol] = {
                "mode": "delta",
                "prior_input_sha256": sha256_payload(previous_rows),
                "rows": appended_rows,
                "current_input_sha256": sha256_payload(current_rows),
                "current_tail_count": len(current_rows),
                "current_tail_end_ms": int(current_rows[-1][0]),
            }
        else:
            replay_by_symbol[symbol] = {
                "mode": "checkpoint",
                "rows": current_rows,
                "current_input_sha256": sha256_payload(current_rows),
                "current_tail_count": len(current_rows),
                "current_tail_end_ms": int(current_rows[-1][0]),
            }
    body: dict[str, Any] = {
        "schema_id": REPLAY_SCHEMA_ID,
        "scope": "score_replay_delta_chain_source_hashes_asserted_not_replayed",
        "source_id": SOURCE_ID,
        "research_only": True,
        "executable": False,
        "sequence": payload["sequence"],
        "as_of_ms": payload["as_of_ms"],
        "config_sha256": config.config_sha256,
        "source_receipts": payload["source_receipts"],
        "replay_by_symbol": replay_by_symbol,
    }
    uncompressed = canonical_bytes(body)
    if len(uncompressed) > config.max_replay_uncompressed_bytes:
        raise EventUniverseError("normalized replay exceeds the frozen uncompressed cap")
    compressed = gzip.compress(uncompressed, compresslevel=9, mtime=0)
    if len(compressed) > config.max_response_bytes:
        raise EventUniverseError("normalized replay exceeds the frozen compressed cap")
    compressed_hash = hashlib.sha256(compressed).hexdigest()
    uncompressed_hash = hashlib.sha256(uncompressed).hexdigest()
    metadata = {
        "schema_id": REPLAY_SCHEMA_ID,
        "scope": "score_replay_delta_chain_source_hashes_asserted_not_replayed",
        "file": f"replay_objects/{uncompressed_hash}.json.gz",
        "compression": "gzip",
        "compressed_sha256": compressed_hash,
        "uncompressed_sha256": uncompressed_hash,
        "compressed_bytes": len(compressed),
        "uncompressed_bytes": len(uncompressed),
        "symbol_count": len(normalized),
    }
    bound = dict(payload)
    bound["replay_bundle"] = metadata
    bound.pop("snapshot_sha256", None)
    bound["snapshot_sha256"] = sha256_payload(bound)
    validate_snapshot_payload(bound, config=config, require_replay=True)
    return bound, compressed


def _decode_and_validate_replay(
    compressed: bytes,
    *,
    snapshot: Mapping[str, Any],
    previous_normalized_m5_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
    config: EventUniverseConfigV1,
) -> tuple[dict[str, Any], dict[str, list[list[Any]]]]:
    metadata = snapshot.get("replay_bundle")
    if not isinstance(metadata, Mapping):
        raise EventUniverseError("normalized replay metadata is missing")
    if len(compressed) != metadata.get("compressed_bytes"):
        raise EventUniverseError("normalized replay compressed length mismatch")
    if hashlib.sha256(compressed).hexdigest() != metadata.get("compressed_sha256"):
        raise EventUniverseError("normalized replay compressed checksum mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as archive:
        uncompressed = archive.read(config.max_replay_uncompressed_bytes + 1)
    if len(uncompressed) > config.max_replay_uncompressed_bytes:
        raise EventUniverseError("normalized replay decompression cap exceeded")
    if len(uncompressed) != metadata.get("uncompressed_bytes"):
        raise EventUniverseError("normalized replay uncompressed length mismatch")
    if hashlib.sha256(uncompressed).hexdigest() != metadata.get("uncompressed_sha256"):
        raise EventUniverseError("normalized replay uncompressed checksum mismatch")
    try:
        body = json.loads(uncompressed.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventUniverseError("normalized replay is not valid UTF-8 JSON") from exc
    if not isinstance(body, dict):
        raise EventUniverseError("normalized replay root is not an object")
    expected_identity = {
        "schema_id": REPLAY_SCHEMA_ID,
        "scope": "score_replay_delta_chain_source_hashes_asserted_not_replayed",
        "source_id": SOURCE_ID,
        "research_only": True,
        "executable": False,
        "sequence": snapshot["sequence"],
        "as_of_ms": snapshot["as_of_ms"],
        "config_sha256": config.config_sha256,
        "source_receipts": snapshot["source_receipts"],
    }
    if any(body.get(key) != value for key, value in expected_identity.items()):
        raise EventUniverseError("normalized replay identity/source receipts mismatch")
    replay_by_symbol = body.get("replay_by_symbol")
    if not isinstance(replay_by_symbol, Mapping):
        raise EventUniverseError("normalized replay delta map is missing")
    scores = snapshot["scores"]
    if set(replay_by_symbol) != {str(score["symbol"]) for score in scores}:
        raise EventUniverseError("normalized replay symbol coverage mismatch")
    if metadata.get("symbol_count") != len(replay_by_symbol):
        raise EventUniverseError("normalized replay symbol count mismatch")
    tier_by_symbol = {
        str(row["symbol"]): str(row["listing_tier"])
        for row in snapshot["universe"]
    }
    score_by_symbol = {str(score["symbol"]): score for score in scores}
    normalized: dict[str, list[list[Any]]] = {}
    for symbol, entry in replay_by_symbol.items():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("rows"), list):
            raise EventUniverseError("normalized replay symbol delta is invalid")
        mode = entry.get("mode")
        if mode == "checkpoint":
            if set(entry) != {
                "mode",
                "rows",
                "current_input_sha256",
                "current_tail_count",
                "current_tail_end_ms",
            }:
                raise EventUniverseError("normalized replay checkpoint fields mismatch")
            rows = [list(row) for row in entry["rows"]]
        elif mode == "delta":
            if set(entry) != {
                "mode",
                "prior_input_sha256",
                "rows",
                "current_input_sha256",
                "current_tail_count",
                "current_tail_end_ms",
            }:
                raise EventUniverseError("normalized replay delta fields mismatch")
            previous_rows = [list(row) for row in previous_normalized_m5_by_symbol.get(symbol, ())]
            if not previous_rows or sha256_payload(previous_rows) != entry.get("prior_input_sha256"):
                raise EventUniverseError("normalized replay delta prior tail mismatch")
            appended = [list(row) for row in entry["rows"]]
            if any(int(row[0]) <= int(previous_rows[-1][0]) for row in appended):
                raise EventUniverseError("normalized replay delta is not append-only")
            rows = (previous_rows + appended)[-config.required_closed_bars :]
        else:
            raise EventUniverseError("normalized replay mode is invalid")
        if len(rows) != config.required_closed_bars:
            raise EventUniverseError("normalized replay tail length mismatch")
        if entry.get("current_tail_count") != len(rows) or entry.get("current_tail_end_ms") != int(rows[-1][0]):
            raise EventUniverseError("normalized replay tail identity mismatch")
        if sha256_payload(rows) != entry.get("current_input_sha256"):
            raise EventUniverseError("normalized replay current tail checksum mismatch")
        if sha256_payload(rows) != score_by_symbol[symbol]["input_sha256"]:
            raise EventUniverseError("normalized replay input checksum mismatch")
        replayed = score_event_m5(
            symbol,
            rows,
            as_of_ms=int(snapshot["as_of_ms"]),
            listing_tier=tier_by_symbol[symbol],
            config=config,
        ).payload()
        if replayed != score_by_symbol[symbol]:
            raise EventUniverseError("normalized replay does not reproduce the stored score")
        normalized[symbol] = rows
    return body, normalized


def _validate_replay_object(
    root: Path,
    snapshot: Mapping[str, Any],
    *,
    previous_normalized_m5_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
    config: EventUniverseConfigV1,
) -> dict[str, list[list[Any]]]:
    metadata = snapshot["replay_bundle"]
    relative = Path(str(metadata["file"]))
    if relative.parts != ("replay_objects", f"{metadata['uncompressed_sha256']}.json.gz"):
        raise EventUniverseError("normalized replay object path is invalid")
    path = root / relative
    compressed = _read_regular_bytes(path, max_bytes=config.max_response_bytes)
    _body, normalized = _decode_and_validate_replay(
        compressed,
        snapshot=snapshot,
        previous_normalized_m5_by_symbol=previous_normalized_m5_by_symbol,
        config=config,
    )
    return normalized


def _load_chain(
    root: Path,
    *,
    config: EventUniverseConfigV1,
) -> ChainState:
    count = 0
    last_path: Path | None = None
    last_payload: dict[str, Any] | None = None
    normalized_m5_by_symbol: dict[str, list[list[Any]]] = {}
    previous_hash: str | None = None
    previous_as_of_ms: int | None = None
    for expected_sequence, path in enumerate(sorted(root.glob("snapshot_*.json.gz")), 1):
        payload = _read_snapshot_regular(path, config=config)
        validate_snapshot_payload(payload, config=config, require_replay=True)
        if payload.get("sequence") != expected_sequence:
            raise EventUniverseError("snapshot sequence is not contiguous")
        if payload.get("previous_snapshot_sha256") != previous_hash:
            raise EventUniverseError("snapshot hash chain is broken")
        if previous_as_of_ms is not None and int(payload["as_of_ms"]) <= previous_as_of_ms:
            raise EventUniverseError("snapshot point-in-time chronology is not strictly increasing")
        expected_name = f"snapshot_{expected_sequence:06d}_{int(payload['as_of_ms'])}.json.gz"
        if path.name != expected_name:
            raise EventUniverseError("snapshot filename/identity mismatch")
        normalized_m5_by_symbol = _validate_replay_object(
            root,
            payload,
            previous_normalized_m5_by_symbol=normalized_m5_by_symbol,
            config=config,
        )
        previous_hash = str(payload["snapshot_sha256"])
        previous_as_of_ms = int(payload["as_of_ms"])
        count = expected_sequence
        last_path = path
        last_payload = payload
    return count, last_path, last_payload, normalized_m5_by_symbol


def _latest_payload(snapshot_path: Path, snapshot: Mapping[str, Any], *, config: EventUniverseConfigV1) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_id": LATEST_SCHEMA_ID,
        "research_only": True,
        "executable": False,
        "config_sha256": config.config_sha256,
        "sequence": snapshot["sequence"],
        "as_of_ms": snapshot["as_of_ms"],
        "snapshot_file": snapshot_path.name,
        "snapshot_sha256": snapshot["snapshot_sha256"],
    }
    body["state_sha256"] = sha256_payload(body)
    return body


def _tree_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode):
            raise EventUniverseError("research run tree contains a symlink")
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
    return total


def _precycle_storage_guard(root: Path, *, config: EventUniverseConfigV1) -> None:
    # Reserve enough room for the maximum compressed replay object plus one
    # maximum snapshot temp file.  No public request begins if the append could
    # not be published under the frozen STOP_NO_DELETE contract.
    reserve = config.max_response_bytes * 2
    if _tree_bytes(root) + reserve > config.max_total_bytes:
        raise EventUniverseError("event-universe run lacks frozen append reserve")
    if shutil.disk_usage(root).free < config.min_free_bytes + reserve:
        raise EventUniverseError("event-universe run lacks frozen free-space reserve")


def persist_snapshot(
    root: Path,
    payload: Mapping[str, Any],
    *,
    replay_bytes: bytes,
    config: EventUniverseConfigV1,
    chain_state: ChainState | None = None,
) -> Path:
    root = _research_root(root)
    validate_snapshot_payload(payload, config=config, require_replay=True)
    if chain_state is None:
        chain_state = _load_chain(root, config=config)
    chain_count, _last_path, last_payload, previous_normalized = chain_state
    _decode_and_validate_replay(
        replay_bytes,
        snapshot=payload,
        previous_normalized_m5_by_symbol=previous_normalized,
        config=config,
    )
    expected_sequence = chain_count + 1
    if payload.get("sequence") != expected_sequence:
        raise EventUniverseError("new snapshot sequence mismatch")
    previous_hash = last_payload["snapshot_sha256"] if last_payload else None
    if payload.get("previous_snapshot_sha256") != previous_hash:
        raise EventUniverseError("new snapshot previous hash mismatch")
    if last_payload is not None and int(payload["as_of_ms"]) <= int(last_payload["as_of_ms"]):
        raise EventUniverseError("new snapshot point-in-time is not strictly increasing")
    if expected_sequence > config.max_snapshots:
        raise EventUniverseError("snapshot count reached frozen stop cap")
    raw_snapshot = canonical_bytes(payload)
    if len(raw_snapshot) > MAX_SNAPSHOT_BYTES:
        raise EventUniverseError("event-universe snapshot exceeds frozen byte cap")
    data = gzip.compress(raw_snapshot, compresslevel=9, mtime=0)
    if len(data) > config.max_response_bytes:
        raise EventUniverseError("event-universe compressed snapshot exceeds frozen byte cap")
    replay_relative = Path(str(payload["replay_bundle"]["file"]))
    replay_path = root / replay_relative
    replay_added_bytes = 0
    if replay_path.exists():
        if _read_regular_bytes(replay_path, max_bytes=config.max_response_bytes) != replay_bytes:
            raise EventUniverseError("content-addressed replay object collision")
    else:
        replay_added_bytes = len(replay_bytes)
    if _tree_bytes(root) + replay_added_bytes + len(data) > config.max_total_bytes:
        raise EventUniverseError("event-universe run reached frozen byte cap")
    if shutil.disk_usage(root).free < config.min_free_bytes + replay_added_bytes + len(data):
        raise EventUniverseError("event-universe run reached minimum free-space guard")
    if not replay_path.exists():
        _atomic_write(replay_path, replay_bytes, replace=False)
    path = root / f"snapshot_{expected_sequence:06d}_{int(payload['as_of_ms'])}.json.gz"
    _atomic_write(path, data, replace=False)
    latest = _latest_payload(path, payload, config=config)
    _atomic_write(root / "latest_state.json", canonical_bytes(latest) + b"\n", replace=True)
    return path


def _status_from_chain(chain_state: ChainState, *, config: EventUniverseConfigV1) -> dict[str, Any]:
    chain_count, _chain_last_path, latest, _normalized = chain_state
    return {
        "schema_id": "event_universe_status_v1",
        "research_only": True,
        "executable": False,
        "config_sha256": config.config_sha256,
        "snapshot_count": chain_count,
        "last_as_of_ms": latest.get("as_of_ms") if latest else None,
        "last_snapshot_sha256": latest.get("snapshot_sha256") if latest else None,
        "last_event_candidate_count": latest.get("event_candidate_count") if latest else None,
        "last_score_count": latest.get("score_count") if latest else None,
    }


def _validate_latest_state(root: Path, chain_state: ChainState, *, config: EventUniverseConfigV1) -> None:
    chain_count, chain_last_path, latest, _normalized = chain_state
    latest_path = root / "latest_state.json"
    if latest is None:
        if latest_path.exists():
            raise EventUniverseError("latest state exists without an immutable snapshot")
    else:
        if not latest_path.exists():
            raise EventUniverseError("latest state is missing")
        state = _read_json_regular(latest_path)
        expected_state = dict(state)
        observed_state_hash = str(expected_state.pop("state_sha256", ""))
        if not _SHA256_RE.fullmatch(observed_state_hash) or observed_state_hash != sha256_payload(expected_state):
            raise EventUniverseError("latest state checksum mismatch")
        assert chain_last_path is not None
        expected_latest = _latest_payload(chain_last_path, latest, config=config)
        if state != expected_latest:
            raise EventUniverseError("latest state does not match the immutable chain head")


def read_status(root: Path, *, config: EventUniverseConfigV1) -> dict[str, Any]:
    root = _research_root(root, create=False)
    chain_state = _load_chain(root, config=config)
    _validate_latest_state(root, chain_state, config=config)
    return _status_from_chain(chain_state, config=config)


def _collect_once_with_state(
    *,
    root: Path,
    spec: Mapping[str, Any],
    config: EventUniverseConfigV1,
    client: PublicBybitEventClientV1,
    chain_state: ChainState,
) -> tuple[Path, dict[str, Any], ChainState]:
    root = _research_root(root)
    _precycle_storage_guard(root, config=config)
    client.start_cycle()
    chain_count, _last_path, last_payload, previous_normalized = chain_state
    sequence = chain_count + 1
    previous_hash = last_payload["snapshot_sha256"] if last_payload else None

    instruments, instrument_hashes, instrument_time = client.fetch_instruments()
    tickers, ticker_hash, ticker_time = client.fetch_tickers()
    as_of_ms = max(instrument_time, ticker_time)
    if last_payload is not None and as_of_ms <= int(last_payload["as_of_ms"]):
        raise EventUniverseError("public point-in-time cutoff did not advance")
    ticker_by_symbol = {str(item.get("symbol") or "").upper(): item for item in tickers}
    market_rows = [
        evaluate_market_eligibility(
            instrument,
            ticker_by_symbol.get(str(instrument.get("symbol") or "").upper()),
            as_of_ms=as_of_ms,
            config=config,
        )
        for instrument in instruments
    ]
    prefetch = select_prefetch_symbols(market_rows, config=config)
    market_by_symbol = {row.symbol: row for row in market_rows}
    scores: list[EventScoreV1] = []
    errors: dict[str, str] = {}
    kline_hashes: dict[str, str] = {}
    normalized_m5_by_symbol: dict[str, list[list[Any]]] = {}
    public_io = spec["public_io"]
    kline_limit = _exact_int(public_io["kline_limit"], "kline limit", positive=True)
    if kline_limit < config.required_closed_bars + 1 or kline_limit > 1000:
        raise EventUniverseError("frozen kline limit cannot provide the required closed tail")
    for symbol in prefetch:
        try:
            raw_rows, source_hash = client.fetch_m5(symbol, as_of_ms=as_of_ms, limit=kline_limit)
            kline_hashes[symbol] = source_hash
            normalized_rows = closed_contiguous_m5(
                raw_rows,
                as_of_ms=as_of_ms,
                required_bars=config.required_closed_bars,
            )
            normalized_payload = [row.payload() for row in normalized_rows]
            scores.append(
                score_event_m5(
                    symbol,
                    normalized_payload,
                    as_of_ms=as_of_ms,
                    listing_tier=market_by_symbol[symbol].listing_tier,
                    config=config,
                )
            )
            normalized_m5_by_symbol[symbol] = normalized_payload
        except (EventUniverseError, KeyError, TypeError, ValueError) as exc:
            errors[symbol] = f"{type(exc).__name__}:{exc}"
    payload = build_snapshot_payload(
        as_of_ms=as_of_ms,
        config=config,
        instruments_page_sha256=instrument_hashes,
        tickers_sha256=ticker_hash,
        market_rows=market_rows,
        prefetch_symbols=prefetch,
        scores=scores,
        errors_by_symbol=errors,
        sequence=sequence,
        previous_snapshot_sha256=previous_hash,
    )
    payload["source_receipts"]["kline_sha256_by_symbol"] = dict(sorted(kline_hashes.items()))
    # The self hash must bind the per-symbol public source receipts too.
    payload.pop("snapshot_sha256")
    payload["snapshot_sha256"] = sha256_payload(payload)
    payload, replay_bytes = _bind_normalized_replay(
        payload,
        normalized_m5_by_symbol,
        previous_normalized_m5_by_symbol=previous_normalized,
        config=config,
    )
    path = persist_snapshot(
        root,
        payload,
        replay_bytes=replay_bytes,
        config=config,
        chain_state=chain_state,
    )
    next_state: ChainState = (sequence, path, payload, normalized_m5_by_symbol)
    return path, payload, next_state


def collect_once(
    *,
    root: Path,
    spec: Mapping[str, Any],
    config: EventUniverseConfigV1,
    client: PublicBybitEventClientV1,
) -> tuple[Path, dict[str, Any]]:
    root = _research_root(root)
    chain_state = _load_chain(root, config=config)
    path, payload, _next_state = _collect_once_with_state(
        root=root,
        spec=spec,
        config=config,
        client=client,
        chain_state=chain_state,
    )
    return path, payload


def _preflight(spec_path: Path) -> dict[str, Any]:
    payload, config = _load_spec(spec_path)
    return {
        "schema_id": "event_universe_preflight_v1",
        "ok": True,
        "status": payload["status"],
        "spec": str(spec_path),
        "spec_sha256": sha256_payload(payload),
        "config_sha256": config.config_sha256,
        "default_enabled": False,
        "network_calls": False,
        "filesystem_writes": False,
        "daemon_started": False,
        "public_method": "GET_ONLY",
        "public_host": PUBLIC_HOST,
        "public_paths": list(PUBLIC_PATHS),
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "risk_or_live_router_mutation": False,
        "executable": False,
        "performance_claims": False,
        "rank_semantics": "heuristic_rank_not_probability",
        "replay_scope": "score_replay_delta_chain_source_hashes_asserted_not_replayed",
        "bounds": {
            "max_prefetch_symbols": config.max_prefetch_symbols,
            "top_k": config.top_k,
            "max_cycle_seconds": config.max_cycle_seconds,
            "max_source_time_skew_ms": config.max_source_time_skew_ms,
            "max_runtime_seconds": config.max_runtime_seconds,
            "max_snapshots": config.max_snapshots,
            "max_total_bytes": config.max_total_bytes,
            "min_free_bytes": config.min_free_bytes,
            "public_requests_per_second": config.public_requests_per_second,
        },
    }


def _client_from_spec(spec: Mapping[str, Any], config: EventUniverseConfigV1) -> PublicBybitEventClientV1:
    public_io = spec["public_io"]
    return PublicBybitEventClientV1(
        config=config,
        timeout_seconds=float(public_io["timeout_seconds"]),
        max_retries=int(public_io["max_retries"]),
        backoff_base_seconds=float(public_io["backoff_base_seconds"]),
    )


def _require_collection_opt_ins(args: argparse.Namespace) -> None:
    missing = []
    if not args.allow_public_network:
        missing.append("--allow-public-network")
    if not args.enable_durable_collector:
        missing.append("--enable-durable-collector")
    if not args.acknowledge_research_only:
        missing.append("--acknowledge-research-only")
    if missing:
        raise EventUniverseError("collection requires explicit opt-ins: " + ", ".join(missing))


def _launch_receipt(root: Path, *, spec: Mapping[str, Any], config: EventUniverseConfigV1) -> dict[str, Any]:
    root = _research_root(root)
    path = root / "launch_receipt.json"
    if path.exists():
        payload = _read_json_regular(path)
        if payload.get("schema_id") != LAUNCH_SCHEMA_ID or payload.get("config_sha256") != config.config_sha256:
            raise EventUniverseError("launch receipt identity mismatch")
        body = dict(payload)
        observed_hash = str(body.pop("launch_sha256", ""))
        if observed_hash != sha256_payload(body):
            raise EventUniverseError("launch receipt checksum mismatch")
        frozen_identity = {
            "research_only": True,
            "executable": False,
            "api_keys_or_environment_reads": False,
            "private_api_calls": False,
            "broker_calls": False,
            "orders_or_risk_mutation": False,
            "spec_sha256": sha256_payload(spec),
            "config_sha256": config.config_sha256,
            "implementation_sha256_by_path": _implementation_sha256_by_path(),
            "poll_interval_seconds": config.poll_interval_seconds,
            "max_snapshots": config.max_snapshots,
            "max_total_bytes": config.max_total_bytes,
        }
        if any(payload.get(key) != value for key, value in frozen_identity.items()):
            raise EventUniverseError("launch receipt no longer matches frozen spec/implementation")
        started_ms = _exact_int(payload.get("started_at_ms"), "launch started_at_ms", positive=True)
        deadline_ms = _exact_int(payload.get("deadline_at_ms"), "launch deadline_at_ms", positive=True)
        if deadline_ms != started_ms + config.max_runtime_seconds * 1000:
            raise EventUniverseError("launch receipt deadline bound is invalid")
        if int(time.time() * 1000) >= deadline_ms:
            raise EventUniverseError("event-universe launch deadline has expired")
        return payload
    started_ms = int(time.time() * 1000)
    body: dict[str, Any] = {
        "schema_id": LAUNCH_SCHEMA_ID,
        "research_only": True,
        "executable": False,
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "spec_sha256": sha256_payload(spec),
        "config_sha256": config.config_sha256,
        "implementation_sha256_by_path": _implementation_sha256_by_path(),
        "started_at_ms": started_ms,
        "deadline_at_ms": started_ms + config.max_runtime_seconds * 1000,
        "poll_interval_seconds": config.poll_interval_seconds,
        "max_snapshots": config.max_snapshots,
        "max_total_bytes": config.max_total_bytes,
    }
    body["launch_sha256"] = sha256_payload(body)
    _atomic_write(path, canonical_bytes(body) + b"\n", replace=False)
    return body


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", help="No-network/no-write safety receipt (default).")
    status = sub.add_parser("status", help="No-network deterministic snapshot-chain status.")
    status.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    for name in ("collect-once", "run"):
        cmd = sub.add_parser(name, help="Public research collection; no credentials or execution.")
        cmd.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
        cmd.add_argument("--allow-public-network", action="store_true")
        cmd.add_argument("--enable-durable-collector", action="store_true")
        cmd.add_argument("--acknowledge-research-only", action="store_true")
        if name == "run":
            cmd.add_argument("--max-cycles-this-process", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "preflight"
    try:
        spec, config = _load_spec(args.spec)
        if command == "preflight":
            print(json.dumps(_preflight(args.spec), indent=2, sort_keys=True))
            return 0
        if command == "status":
            print(json.dumps(read_status(args.run_root, config=config), indent=2, sort_keys=True))
            return 0
        _require_collection_opt_ins(args)
        client = _client_from_spec(spec, config)
        with _single_writer_lock(args.run_root):
            launch = _launch_receipt(args.run_root, spec=spec, config=config)
            root = _research_root(args.run_root)
            chain_state = _load_chain(root, config=config)
            _validate_latest_state(root, chain_state, config=config)
            if command == "collect-once":
                path, payload, chain_state = _collect_once_with_state(
                    root=root,
                    spec=spec,
                    config=config,
                    client=client,
                    chain_state=chain_state,
                )
                print(
                    json.dumps(
                        {
                            "snapshot": str(path),
                            "sequence": payload["sequence"],
                            "as_of_ms": payload["as_of_ms"],
                            "universe_count": len(payload["universe"]),
                            "prefetch_count": payload["prefetch_count"],
                            "score_count": payload["score_count"],
                            "event_candidate_count": payload["event_candidate_count"],
                            "research_only": True,
                            "executable": False,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0

            max_cycles = args.max_cycles_this_process
            if max_cycles is not None and max_cycles <= 0:
                raise EventUniverseError("max cycles must be positive")
            completed = 0
            while int(time.time() * 1000) < int(launch["deadline_at_ms"]):
                status = _status_from_chain(chain_state, config=config)
                if status["snapshot_count"] >= config.max_snapshots:
                    break
                cycle_started = time.monotonic()
                path, payload, chain_state = _collect_once_with_state(
                    root=root,
                    spec=spec,
                    config=config,
                    client=client,
                    chain_state=chain_state,
                )
                completed += 1
                print(
                    json.dumps(
                        {
                            "snapshot": str(path),
                            "sequence": payload["sequence"],
                            "as_of_ms": payload["as_of_ms"],
                            "score_count": payload["score_count"],
                            "event_candidate_count": payload["event_candidate_count"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                if max_cycles is not None and completed >= max_cycles:
                    break
                remaining = config.poll_interval_seconds - (time.monotonic() - cycle_started)
                if remaining > 0:
                    time.sleep(remaining)
            print(json.dumps(_status_from_chain(chain_state, config=config), indent=2, sort_keys=True))
            return 0
    except (EventUniverseError, KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True),
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
