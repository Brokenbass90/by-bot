"""Fail-closed canonical public H1 cache and research feed."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Iterable, Sequence

from research_lab.research_ohlcv_store import ResearchKlineStore, ResearchKlineStoreError, timeframe_minutes


H1_MS = 3_600_000
SCHEMA_ID = "public_h1_cache_v1"
_SYMBOL = re.compile(r"[A-Z0-9]{2,40}\Z")


class PublicCacheViolation(ValueError):
    """Stable fail-closed error for malformed, stale, or unsafe public data."""


def _integer(value: object, what: str) -> int:
    if isinstance(value, bool):
        raise PublicCacheViolation(f"{what} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PublicCacheViolation(f"{what} must be an integer") from exc
    if isinstance(value, float) and value != result:
        raise PublicCacheViolation(f"{what} must be an integer")
    return result


def _row(raw: Sequence[object], index: int) -> list[float | int]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence) or len(raw) < 6:
        raise PublicCacheViolation(f"row {index} must contain six OHLCV fields")
    ts = _integer(raw[0], f"row {index} timestamp")
    try:
        values = [float(raw[offset]) for offset in range(1, 6)]
    except (TypeError, ValueError, OverflowError) as exc:
        raise PublicCacheViolation(f"row {index} contains non-numeric OHLCV") from exc
    if ts < 0 or any(not math.isfinite(value) for value in values):
        raise PublicCacheViolation(f"row {index} contains non-finite OHLCV")
    open_, high, low, close, volume = values
    if min(open_, high, low, close) <= 0 or volume < 0:
        raise PublicCacheViolation(f"row {index} contains invalid OHLCV")
    if high < max(open_, close) or low > min(open_, close) or low > high:
        raise PublicCacheViolation(f"row {index} has invalid OHLC geometry")
    return [ts, open_, high, low, close, volume]


def validate_closed_h1_rows(
    rows: Iterable[Sequence[object]],
    observed_at_ms: int,
    *,
    min_bars: int = 1,
    max_age_ms: int | None = None,
) -> list[list[float | int]]:
    """Normalize Bybit/common rows and return only complete, contiguous H1 bars."""

    observed = _integer(observed_at_ms, "observed_at_ms")
    if observed < 0:
        raise PublicCacheViolation("observed_at_ms must be non-negative")
    if isinstance(min_bars, bool) or not isinstance(min_bars, Integral) or int(min_bars) < 0:
        raise PublicCacheViolation("minimum bar count is invalid")
    if max_age_ms is not None and (
        isinstance(max_age_ms, bool) or not isinstance(max_age_ms, Integral) or int(max_age_ms) < 0
    ):
        raise PublicCacheViolation("max_age_ms is invalid")
    try:
        normalized = [_row(raw, index) for index, raw in enumerate(rows)]
    except TypeError as exc:
        raise PublicCacheViolation("rows must be iterable") from exc
    if normalized:
        timestamps = [int(item[0]) for item in normalized]
        if len(set(timestamps)) != len(timestamps):
            raise PublicCacheViolation("duplicate H1 timestamp")
        increasing = all(right > left for left, right in zip(timestamps, timestamps[1:]))
        decreasing = all(right < left for left, right in zip(timestamps, timestamps[1:]))
        if not (increasing or decreasing):
            raise PublicCacheViolation("rows must be strictly ordered")
        if decreasing:
            normalized.reverse()
        for item in normalized:
            if int(item[0]) % H1_MS:
                raise PublicCacheViolation("H1 timestamp is off-grid")
            if int(item[0]) > observed:
                raise PublicCacheViolation("future H1 data")
        while normalized and int(normalized[-1][0]) + H1_MS > observed:
            normalized.pop()
        if normalized:
            for left, right in zip(normalized, normalized[1:]):
                if int(right[0]) - int(left[0]) != H1_MS:
                    raise PublicCacheViolation("H1 rows have a gap and are not contiguous")
    if len(normalized) < int(min_bars):
        raise PublicCacheViolation("history is below minimum bar count")
    if normalized and max_age_ms is not None:
        latest_close = int(normalized[-1][0]) + H1_MS
        if observed - latest_close > int(max_age_ms):
            raise PublicCacheViolation("latest H1 close is stale")
    return normalized


def classify_stream(*, bar_close_ts_ms: int, observed_at_ms: int, max_forward_lag_ms: int) -> str:
    """Classify a close observation without accepting clock-skewed data."""

    close = _integer(bar_close_ts_ms, "bar_close_ts_ms")
    observed = _integer(observed_at_ms, "observed_at_ms")
    lag = _integer(max_forward_lag_ms, "max_forward_lag_ms")
    if lag < 0:
        raise PublicCacheViolation("max_forward_lag_ms must be non-negative")
    if observed < close:
        raise PublicCacheViolation("observation is before bar close")
    if observed - close <= lag:
        return "EXECUTION_FORWARD"
    return "ALPHA_FORWARD_BACKFILL"


def _canonical_rows(rows: Sequence[Sequence[object]]) -> bytes:
    return json.dumps([list(row) for row in rows], separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _rows_hash(rows: Sequence[Sequence[object]]) -> str:
    return hashlib.sha256(_canonical_rows(rows)).hexdigest()


@dataclass(frozen=True)
class CacheMetadata:
    row_count: int
    first_start_ms: int | None
    last_start_ms: int | None
    latest_close_ms: int | None
    rows_hash: str
    changed: bool


def _metadata(rows: Sequence[Sequence[object]], *, changed: bool) -> CacheMetadata:
    return CacheMetadata(
        row_count=len(rows),
        first_start_ms=int(rows[0][0]) if rows else None,
        last_start_ms=int(rows[-1][0]) if rows else None,
        latest_close_ms=int(rows[-1][0]) + H1_MS if rows else None,
        rows_hash=_rows_hash(rows),
        changed=changed,
    )


class CanonicalH1Cache:
    """One atomic, hash-bound JSON snapshot per uppercase symbol."""

    def __init__(self, root: Path | str, max_bars: int):
        if isinstance(max_bars, bool) or not isinstance(max_bars, Integral) or int(max_bars) < 1920:
            raise PublicCacheViolation("max_bars must be at least 1920")
        self.root = Path(os.path.abspath(os.fspath(root)))
        self._check_existing_ancestors()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PublicCacheViolation("cache root is not usable") from exc
        self.max_bars = int(max_bars)
        self._check_root()

    def _check_existing_ancestors(self) -> None:
        current = Path(self.root.anchor or "/")
        for part in self.root.parts[1:]:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                break
            except OSError as exc:
                raise PublicCacheViolation("cache root is not usable") from exc
            if stat.S_ISLNK(info.st_mode):
                raise PublicCacheViolation("cache root has a symlink component")

    def _open_root_fd(self) -> int:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        try:
            current_fd = os.open(self.root.anchor or "/", flags | directory_flag)
            for part in self.root.parts[1:]:
                next_fd = os.open(part, flags | directory_flag, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
            if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
                os.close(current_fd)
                raise PublicCacheViolation("cache root is not a directory")
            return current_fd
        except PublicCacheViolation:
            raise
        except OSError as exc:
            try:
                os.close(current_fd)
            except (OSError, UnboundLocalError):
                pass
            raise PublicCacheViolation("cache root is not usable") from exc

    def _check_root(self) -> None:
        fd = self._open_root_fd()
        os.close(fd)

    @staticmethod
    def _symbol(symbol: str) -> str:
        value = str(symbol or "").strip().upper()
        if _SYMBOL.fullmatch(value) is None:
            raise PublicCacheViolation("unsafe symbol")
        return value

    def _path(self, symbol: str) -> Path:
        self._check_root()
        return self.root / f"{self._symbol(symbol)}.json"

    def _read(self, symbol: str) -> list[list[float | int]]:
        filename = f"{self._symbol(symbol)}.json"
        root_fd = self._open_root_fd()
        file_fd = -1
        try:
            file_fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
        except FileNotFoundError:
            os.close(root_fd)
            return []
        except OSError as exc:
            os.close(root_fd)
            if getattr(exc, "errno", None) == getattr(os, "ELOOP", 62):
                raise PublicCacheViolation("cache file is a symlink") from exc
            raise PublicCacheViolation("cache file cannot be inspected") from exc
        finally:
            if file_fd >= 0:
                os.close(root_fd)
        info = os.fstat(file_fd)
        if stat.S_ISLNK(info.st_mode):
            os.close(file_fd)
            raise PublicCacheViolation("cache file is a symlink")
        if not stat.S_ISREG(info.st_mode):
            os.close(file_fd)
            raise PublicCacheViolation("cache file is not regular")
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.close(file_fd)
            raise PublicCacheViolation("cache file mode must be 0600")
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = json.loads(b"".join(chunks).decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PublicCacheViolation("corrupt cache file") from exc
        finally:
            os.close(file_fd)
        if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_ID or raw.get("symbol") != self._symbol(symbol):
            raise PublicCacheViolation("corrupt cache schema")
        rows = raw.get("rows")
        if not isinstance(rows, list):
            raise PublicCacheViolation("corrupt cache rows")
        try:
            checked = validate_closed_h1_rows(rows, int(rows[-1][0]) + H1_MS if rows else 0, min_bars=0)
        except (PublicCacheViolation, TypeError, ValueError) as exc:
            raise PublicCacheViolation("corrupt cache rows") from exc
        if len(checked) > self.max_bars or raw.get("row_count") != len(checked) or raw.get("rows_hash") != _rows_hash(checked):
            raise PublicCacheViolation("corrupt cache hash or metadata")
        expected = _metadata(checked, changed=False)
        if raw.get("first_start_ms") != expected.first_start_ms or raw.get("last_start_ms") != expected.last_start_ms or raw.get("latest_close_ms") != expected.latest_close_ms:
            raise PublicCacheViolation("corrupt cache metadata")
        return checked

    def load(self, symbol: str) -> tuple[tuple[list[float | int], ...], CacheMetadata]:
        rows = self._read(symbol)
        return tuple(rows), _metadata(rows, changed=False)

    def _write(self, symbol: str, rows: Sequence[Sequence[object]]) -> None:
        normalized_symbol = self._symbol(symbol)
        filename = f"{normalized_symbol}.json"
        payload = {
            "schema": SCHEMA_ID,
            "symbol": normalized_symbol,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "first_start_ms": int(rows[0][0]) if rows else None,
            "last_start_ms": int(rows[-1][0]) if rows else None,
            "latest_close_ms": int(rows[-1][0]) + H1_MS if rows else None,
            "rows_hash": _rows_hash(rows),
        }
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        root_fd = self._open_root_fd()
        temp_fd = -1
        temp_name = ""
        try:
            temp_name = f".{normalized_symbol}.{secrets.token_hex(12)}.tmp"
            temp_fd = os.open(
                temp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root_fd,
            )
            os.fchmod(temp_fd, 0o600)
            view = memoryview(data)
            while view:
                view = view[os.write(temp_fd, view) :]
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = -1
            os.replace(temp_name, filename, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError as exc:
            if temp_fd >= 0:
                os.close(temp_fd)
            if temp_name:
                try:
                    os.unlink(temp_name, dir_fd=root_fd)
                except OSError:
                    pass
            raise PublicCacheViolation("atomic cache write failed") from exc
        finally:
            os.close(root_fd)

    def merge(
        self, symbol: str, closed_rows: Iterable[Sequence[object]], observed_at_ms: int
    ) -> CacheMetadata:
        normalized_symbol = self._symbol(symbol)
        incoming = validate_closed_h1_rows(closed_rows, observed_at_ms, min_bars=0)
        existing = self._read(normalized_symbol)
        if len(existing) == self.max_bars and incoming and int(incoming[0][0]) < int(existing[0][0]):
            raise PublicCacheViolation("incoming H1 precedes retained boundary")
        by_ts: dict[int, list[float | int]] = {int(row[0]): row for row in existing}
        for row in incoming:
            timestamp = int(row[0])
            if timestamp in by_ts and by_ts[timestamp] != row:
                raise PublicCacheViolation("historical H1 mutation")
            by_ts[timestamp] = row
        merged = [by_ts[timestamp] for timestamp in sorted(by_ts)]
        for left, right in zip(merged, merged[1:]):
            if int(right[0]) - int(left[0]) != H1_MS:
                raise PublicCacheViolation("cache rows are not contiguous")
        retained = merged[-self.max_bars :]
        changed = retained != existing
        if changed and retained:
            self._write(normalized_symbol, retained)
        elif changed and not retained:
            # An empty merge is a no-op; a missing cache remains represented by absence.
            pass
        return _metadata(retained, changed=changed)


class CanonicalCachedFeed:
    """``fetch_klines``-compatible H1/H4/D1 feed backed by one closed H1 prefix."""

    def __init__(self, symbol: str, rows: Iterable[Sequence[object]]):
        self.symbol = CanonicalH1Cache._symbol(symbol)
        raw = list(rows)
        if raw:
            parsed = [_row(item, index) for index, item in enumerate(raw)]
            source = validate_closed_h1_rows(raw, max(int(item[0]) for item in parsed) + H1_MS, min_bars=1)
        else:
            source = []
        self.rows = [list(row) for row in source]
        self._store = ResearchKlineStore(self.symbol, base_interval_minutes=60)
        self._store.rows = self.rows

    def __call__(self, symbol: str, timeframe: object, limit: int):
        if symbol != self.symbol:
            raise PublicCacheViolation("feed symbol mismatch")
        try:
            minutes = timeframe_minutes(timeframe)
        except ResearchKlineStoreError as exc:
            raise PublicCacheViolation(f"unsupported timeframe: {timeframe}") from exc
        if minutes not in {60, 240, 1440}:
            raise PublicCacheViolation("unsupported timeframe")
        try:
            return self._store.fetch_klines(symbol, timeframe, limit)
        except ResearchKlineStoreError as exc:
            raise PublicCacheViolation(str(exc)) from exc


__all__ = [
    "CacheMetadata",
    "CanonicalCachedFeed",
    "CanonicalH1Cache",
    "PublicCacheViolation",
    "classify_stream",
    "validate_closed_h1_rows",
]
