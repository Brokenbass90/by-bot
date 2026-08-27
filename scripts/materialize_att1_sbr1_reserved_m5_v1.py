#!/usr/bin/env python3
"""Freeze the reserved ATT1/SBR1 Bybit M5 inputs without scoring them.

This materializer uses only the public Bybit linear kline endpoint when its
explicit acknowledgement is supplied.  It has no private, broker, order, live,
signal, trade, return, or performance paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_public_market_inputs import BYBIT_BASE, _bybit_result, _public_get_json

START_UTC = "2025-10-01T00:00:00Z"
END_UTC_EXCLUSIVE = "2026-07-01T00:00:00Z"


def utc_ms(value: str) -> int:
    """Convert an explicit UTC ISO-8601 instant to epoch milliseconds."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MaterializationError(f"invalid UTC instant: {value!r}") from exc
    if parsed.tzinfo != timezone.utc or not value.endswith("Z"):
        raise MaterializationError(f"instant must be explicit UTC Z: {value!r}")
    return int(parsed.timestamp() * 1000)


START_MS = utc_ms(START_UTC)
END_EXCLUSIVE_MS = utc_ms(END_UTC_EXCLUSIVE)
INTERVAL_MS = 5 * 60 * 1000
EXPECTED_ROWS_PER_SYMBOL = 273 * 288
EXPECTED_UNIVERSE = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT",
)
DEFAULT_OUT_DIR = ROOT / "data_cache/immutable/att1_sbr1_reserved_m5_v1"
DEFAULT_MANIFEST_PATH = ROOT / "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json"
DEFAULT_CANDIDATE_MANIFEST = ROOT / "configs/research/att1_sbr1_live_native_parity_v1.json"
AUTHORITY = "identity_only_materialized_without_scoring_no_live_no_broker"
PAYLOAD_KEYS = frozenset({
    "schema_id", "authority", "symbol", "window", "timeframe_minutes", "records",
    "records_sha256", "performance_computed", "money_authority",
})
RECORD_KEYS = frozenset({"ts_ms", "open", "high", "low", "close", "volume", "turnover"})

JsonGetter = Callable[[str, dict[str, Any]], dict[str, Any]]
Fetcher = Callable[..., list[dict[str, Any]]]


class MaterializationError(RuntimeError):
    """Fail-closed reserved input identity materialization error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"


def _atomic_json(path: Path, payload: Mapping[str, Any], *, replace: bool) -> None:
    if path.is_symlink():
        raise MaterializationError(f"refusing symlink output: {path}")
    if path.exists() and not replace:
        raise MaterializationError(f"refusing to overwrite immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_canonical_json_bytes(payload).decode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def frozen_universe(candidate_manifest: Path) -> list[str]:
    if candidate_manifest.is_symlink() or not candidate_manifest.is_file():
        raise MaterializationError("frozen candidate manifest missing or unsafe")
    try:
        candidate = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializationError("frozen candidate manifest is unreadable") from exc
    universe = candidate.get("universe") if isinstance(candidate, dict) else None
    if universe != list(EXPECTED_UNIVERSE):
        raise MaterializationError("frozen candidate universe changed")
    return list(universe)


def _row(raw: Sequence[Any], symbol: str) -> dict[str, Any]:
    try:
        return {
            "ts_ms": int(raw[0]), "open": float(raw[1]), "high": float(raw[2]),
            "low": float(raw[3]), "close": float(raw[4]), "volume": float(raw[5]),
            "turnover": float(raw[6]),
        }
    except (IndexError, TypeError, ValueError) as exc:
        raise MaterializationError(f"{symbol}: malformed Bybit M5 row") from exc


def fetch_m5(symbol: str, *, start_ms: int = START_MS, end_exclusive_ms: int = END_EXCLUSIVE_MS,
             allow_reserved_public_network: bool = False,
             get_json: JsonGetter = _public_get_json) -> list[dict[str, Any]]:
    """Fetch public Bybit linear M5 history, detecting conflicting duplicates."""
    if not allow_reserved_public_network:
        raise MaterializationError("--allow-reserved-public-network acknowledgement required before any fetch")
    found: dict[int, dict[str, Any]] = {}
    cursor_end = end_exclusive_ms - 1
    for _ in range(400):
        result = _bybit_result(get_json(f"{BYBIT_BASE}/v5/market/kline", {
            "category": "linear", "symbol": symbol, "interval": "5", "start": start_ms,
            "end": cursor_end, "limit": 1000,
        }), f"Bybit reserved M5 {symbol}")
        raw_rows = result.get("list") or []
        if not isinstance(raw_rows, list):
            raise MaterializationError(f"{symbol}: malformed Bybit M5 list")
        if not raw_rows:
            break
        times: list[int] = []
        for raw in raw_rows:
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                raise MaterializationError(f"{symbol}: malformed Bybit M5 row")
            item = _row(raw, symbol)
            ts = item["ts_ms"]
            times.append(ts)
            if start_ms <= ts < end_exclusive_ms:
                prior = found.get(ts)
                if prior is not None and prior != item:
                    raise MaterializationError(f"{symbol}: conflicting duplicate at {ts}")
                found[ts] = item
        oldest = min(times)
        if oldest <= start_ms:
            break
        next_end = oldest - 1
        if next_end >= cursor_end:
            raise MaterializationError(f"{symbol}: pagination stalled")
        cursor_end = next_end
    else:
        raise MaterializationError(f"{symbol}: pagination did not terminate")
    return [found[ts] for ts in sorted(found)]


def validate_rows(rows: Sequence[Mapping[str, Any]], *, symbol: str) -> None:
    if len(rows) != EXPECTED_ROWS_PER_SYMBOL:
        raise MaterializationError(f"{symbol}: expected {EXPECTED_ROWS_PER_SYMBOL} M5 rows, got {len(rows)}")
    timestamps: list[int] = []
    for item in rows:
        if set(item) != RECORD_KEYS:
            raise MaterializationError(f"{symbol}: record schema changed")
        try:
            timestamp = int(item["ts_ms"])
            values = [float(item[key]) for key in ("open", "high", "low", "close")]
        except (KeyError, TypeError, ValueError) as exc:
            raise MaterializationError(f"{symbol}: malformed OHLC row") from exc
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise MaterializationError(f"{symbol}: non-finite or non-positive OHLC at {timestamp}")
        opening, high, low, close = values
        if high < max(opening, close) or low > min(opening, close):
            raise MaterializationError(f"{symbol}: inconsistent OHLC at {timestamp}")
        timestamps.append(timestamp)
    if timestamps[0] != START_MS or timestamps[-1] != END_EXCLUSIVE_MS - INTERVAL_MS:
        raise MaterializationError(f"{symbol}: exact first/last timestamp mismatch")
    if len(set(timestamps)) != len(timestamps):
        raise MaterializationError(f"{symbol}: timestamps must be unique")
    if timestamps != sorted(timestamps):
        raise MaterializationError(f"{symbol}: timestamps must be sorted")
    if any(right - left != INTERVAL_MS for left, right in zip(timestamps, timestamps[1:])):
        raise MaterializationError(f"{symbol}: timestamps must be contiguous M5")


def _payload(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_id": "att1_sbr1_reserved_m5_payload_v1", "authority": AUTHORITY,
        "symbol": symbol, "window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC_EXCLUSIVE},
        "timeframe_minutes": 5, "records": rows, "records_sha256": canonical_sha(rows),
        "performance_computed": False, "money_authority": False,
    }


def _load_verified_payload(path: Path, *, symbol: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise MaterializationError(f"{symbol}: corrupt or drifted payload")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"{symbol}: corrupt or drifted payload") from exc
    expected = {
        "schema_id": "att1_sbr1_reserved_m5_payload_v1", "authority": AUTHORITY, "symbol": symbol,
        "window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC_EXCLUSIVE}, "timeframe_minutes": 5,
        "performance_computed": False, "money_authority": False,
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != PAYLOAD_KEYS
        or any(payload.get(key) != value for key, value in expected.items())
    ):
        raise MaterializationError(f"{symbol}: corrupt or drifted payload")
    rows = payload.get("records")
    if not isinstance(rows, list) or payload.get("records_sha256") != canonical_sha(rows):
        raise MaterializationError(f"{symbol}: corrupt or drifted payload")
    validate_rows(rows, symbol=symbol)
    return payload


def _is_exact_manifest(path: Path, expected: Mapping[str, Any]) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.read_bytes() == _canonical_json_bytes(expected)
    except OSError:
        return False


def _validate_fixed_path(path: Path) -> None:
    """Reject fixed-path symlink escapes before the production CLI uses them."""
    try:
        relative = path.relative_to(ROOT)
    except ValueError as exc:
        raise MaterializationError(f"fixed path escaped repository: {path}") from exc
    cursor = ROOT
    if cursor.is_symlink():
        raise MaterializationError("repository root must not be a symlink")
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise MaterializationError(f"fixed path contains symlink: {cursor}")
    try:
        path.resolve(strict=False).relative_to(ROOT.resolve())
    except ValueError as exc:
        raise MaterializationError(f"fixed path escaped repository: {path}") from exc


def validate_production_paths() -> None:
    for path in (DEFAULT_OUT_DIR, DEFAULT_MANIFEST_PATH, DEFAULT_CANDIDATE_MANIFEST):
        _validate_fixed_path(path)


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _input_identity(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    records = payload["records"]
    assert isinstance(records, list)
    return {
        "symbol": payload["symbol"], "source_path": _repo_relative(path), "sha256": sha256_file(path),
        "bytes": path.stat().st_size, "rows": len(records), "first_ts_ms": records[0]["ts_ms"],
        "last_ts_ms": records[-1]["ts_ms"],
    }


def materialize(*, out_dir: Path = DEFAULT_OUT_DIR, manifest_path: Path = DEFAULT_MANIFEST_PATH,
                candidate_manifest: Path = DEFAULT_CANDIDATE_MANIFEST,
                allow_reserved_public_network: bool = False, fetcher: Fetcher = fetch_m5) -> dict[str, Any]:
    """Materialize all frozen inputs or reuse only payloads that fully validate."""
    symbols = frozen_universe(candidate_manifest)
    verified: list[tuple[Path, dict[str, Any]]] = []
    fetched = False
    for symbol in symbols:
        path = out_dir / f"{symbol}.json"
        try:
            payload = _load_verified_payload(path, symbol=symbol)
        except MaterializationError:
            if path.exists() and not allow_reserved_public_network:
                raise MaterializationError(f"{symbol}: corrupt or drifted payload; acknowledgement required before refetch")
            if not allow_reserved_public_network:
                raise MaterializationError("--allow-reserved-public-network acknowledgement required before any fetch")
            if fetcher is fetch_m5:
                rows = fetcher(
                    symbol, start_ms=START_MS, end_exclusive_ms=END_EXCLUSIVE_MS,
                    allow_reserved_public_network=True,
                )
            else:
                rows = fetcher(symbol, start_ms=START_MS, end_exclusive_ms=END_EXCLUSIVE_MS)
            validate_rows(rows, symbol=symbol)
            payload = _payload(symbol, rows)
            _atomic_json(path, payload, replace=path.exists())
            fetched = True
        verified.append((path, payload))
    manifest = {
        "schema_id": "att1_sbr1_reserved_m5_input_manifest_v1", "authority": AUTHORITY,
        "materializer": {"path": "scripts/materialize_att1_sbr1_reserved_m5_v1.py", "sha256": sha256_file(Path(__file__).resolve())},
        "expected_rows_per_symbol": EXPECTED_ROWS_PER_SYMBOL,
        "public_network_only": True, "private_live_order_authority": False,
        "market_rows_decoded_by_preflight": 0, "performance_computed": False, "money_authority": False,
        "window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC_EXCLUSIVE}, "timeframe_minutes": 5,
        "inputs": [_input_identity(path, payload) for path, payload in verified],
    }
    if manifest_path.exists():
        if _is_exact_manifest(manifest_path, manifest):
            return manifest
        if not fetched:
            raise MaterializationError("input manifest is corrupt or drifted; refuse to rewrite without materialization")
    _atomic_json(manifest_path, manifest, replace=manifest_path.exists())
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-reserved-public-network", action="store_true")
    args = parser.parse_args()
    validate_production_paths()
    print(json.dumps(materialize(allow_reserved_public_network=args.allow_reserved_public_network), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
