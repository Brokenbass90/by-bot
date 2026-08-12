#!/usr/bin/env python3
"""Resumable public Bybit listings and funding archive for research.

This process has no credential, broker, order, transfer, or risk path.  It
materializes the exact symbol inventory present in ``research_lab/data/h1``
by default, including current Bybit ``Trading``, ``PreLaunch`` and ``Closed``
instrument metadata, then downloads Bybit funding history from 2023 onward.
One atomic file per symbol makes the job safely resumable.
``--as-of-exclusive`` can freeze a physically isolated pre-holdout archive
without reading a newer local dataset.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_public_market_inputs import (
    _public_get_json,
    fetch_bybit_funding_history,
    fetch_bybit_linear_universe,
)


DEFAULT_H1_DIR = ROOT / "research_lab/data/h1"
DEFAULT_OUT = ROOT / "research_lab/data/bybit_public_archive_2023"
AUTHORITY = "research_only_public_data_no_orders"
JsonGetter = Callable[[str, dict[str, Any]], dict[str, Any]]


class ArchiveError(RuntimeError):
    """Public archive cannot safely make progress."""


def _canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("wb") as handle:
        handle.write(_canonical_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _parse_day(value: str) -> int:
    parsed = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


def symbols_from_h1(directory: Path) -> list[str]:
    symbols = sorted({path.stem.upper() for path in directory.glob("*.npz")})
    if not symbols:
        raise ArchiveError(f"no H1 NPZ symbols found in {directory}")
    return symbols


def _instrument_interval(row: dict[str, Any], *, requested_start_ms: int, as_of_ms: int) -> tuple[int, int]:
    launch = int(row.get("launchTime") or 0)
    delivery = int(row.get("deliveryTime") or 0)
    start = max(requested_start_ms, launch) if launch > 0 else requested_start_ms
    end = min(as_of_ms, delivery) if delivery > 0 else as_of_ms
    return start, end


def _coverage(records: list[dict[str, Any]], instrument: dict[str, Any], *, requested_start_ms: int, as_of_ms: int) -> dict[str, Any]:
    start, end = _instrument_interval(instrument, requested_start_ms=requested_start_ms, as_of_ms=as_of_ms)
    interval_minutes = int(instrument.get("fundingInterval") or 480)
    expected = max(0, int((end - start) // max(1, interval_minutes * 60_000)) + 1) if end >= start else 0
    times = [int(row["funding_time_ms"]) for row in records]
    unique = len(times) == len(set(times))
    ascending = times == sorted(times)
    ratio = len(times) / expected if expected else None
    return {
        "interval_start_ms": start,
        "interval_end_ms": end,
        "funding_interval_minutes": interval_minutes,
        "expected_observations_upper_bound": expected,
        "observations": len(times),
        "coverage_vs_upper_bound": round(ratio, 6) if ratio is not None else None,
        "first_funding_time_ms": times[0] if times else None,
        "last_funding_time_ms": times[-1] if times else None,
        "timestamps_unique": unique,
        "timestamps_ascending": ascending,
    }


def build_archive(
    *,
    symbols: list[str],
    out_dir: Path,
    start_ms: int,
    as_of_ms: int,
    min_free_gb: float,
    sleep_seconds: float,
    get_json: JsonGetter = _public_get_json,
    max_symbols: int = 0,
) -> dict[str, Any]:
    if shutil.disk_usage(out_dir.parent if out_dir.parent.exists() else ROOT).free < min_free_gb * 1024**3:
        raise ArchiveError(f"disk guard: less than {min_free_gb:g} GiB free")
    universe = fetch_bybit_linear_universe(get_json=get_json)
    records = universe.get("records") or []
    instrument_map = {str(row.get("symbol") or "").upper(): row for row in records}
    universe_payload = {
        "schema_id": "bybit_pit_listing_intervals_v1",
        "authority": AUTHORITY,
        "requested_symbols": symbols,
        "requested_symbol_count": len(symbols),
        "as_of_ms": as_of_ms,
        "provider_snapshot": universe,
        "payload_sha256": _sha256(universe),
    }
    _atomic_json(out_dir / "listing_intervals.json", universe_payload)

    status: dict[str, Any] = {
        "schema_id": "bybit_research_archive_status_v1",
        "authority": AUTHORITY,
        "private_api_calls": False,
        "orders_or_risk_mutation": False,
        "requested_start_ms": start_ms,
        "as_of_ms": as_of_ms,
        "requested_symbol_count": len(symbols),
        "completed": [],
        "skipped_current": [],
        "missing_instrument": [],
        "failed": {},
        "state": "running",
    }
    funding_dir = out_dir / "funding"
    funding_dir.mkdir(parents=True, exist_ok=True)
    attempted = 0
    for symbol in symbols:
        if max_symbols > 0 and attempted >= max_symbols:
            break
        if shutil.disk_usage(out_dir).free < min_free_gb * 1024**3:
            status["state"] = "stopped_disk_guard"
            _atomic_json(out_dir / "status.json", status)
            raise ArchiveError(f"disk guard activated below {min_free_gb:g} GiB")
        instrument = instrument_map.get(symbol)
        if instrument is None:
            status["missing_instrument"].append(symbol)
            _atomic_json(out_dir / "status.json", status)
            continue
        path = funding_dir / f"{symbol}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if (
                    int(existing.get("requested_start_ms") or 0) <= start_ms
                    and int(existing.get("as_of_ms") or 0) >= as_of_ms - 86_400_000
                    and existing.get("payload_sha256") == _sha256(existing.get("records") or [])
                ):
                    status["skipped_current"].append(symbol)
                    continue
            except Exception:
                pass
        attempted += 1
        try:
            rows = fetch_bybit_funding_history(
                symbol,
                cutoff_ms=start_ms,
                as_of_ms=as_of_ms,
                get_json=get_json,
            )
            coverage = _coverage(rows, instrument, requested_start_ms=start_ms, as_of_ms=as_of_ms)
            if not coverage["timestamps_unique"] or not coverage["timestamps_ascending"]:
                raise ArchiveError(f"{symbol}: funding timestamps are not unique and ascending")
            payload = {
                "schema_id": "bybit_public_funding_symbol_v1",
                "authority": AUTHORITY,
                "symbol": symbol,
                "requested_start_ms": start_ms,
                "as_of_ms": as_of_ms,
                "instrument": {
                    key: instrument.get(key)
                    for key in ("symbol", "status", "contractType", "symbolType", "launchTime", "deliveryTime", "fundingInterval")
                },
                "coverage": coverage,
                "records": rows,
                "payload_sha256": _sha256(rows),
            }
            _atomic_json(path, payload)
            status["completed"].append(symbol)
        except Exception as exc:
            status["failed"][symbol] = f"{type(exc).__name__}: {exc}"
        status["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _atomic_json(out_dir / "status.json", status)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    status["state"] = "complete" if max_symbols <= 0 or attempted < max_symbols else "budget_complete"
    status["completed_count"] = len(status["completed"])
    status["skipped_current_count"] = len(status["skipped_current"])
    status["missing_instrument_count"] = len(status["missing_instrument"])
    status["failed_count"] = len(status["failed"])
    status["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _atomic_json(out_dir / "status.json", status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--h1-dir", type=Path, default=DEFAULT_H1_DIR)
    parser.add_argument("--symbols", default="", help="Optional comma-separated override")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument(
        "--as-of-exclusive",
        default="",
        help="Optional YYYY-MM-DD upper bound; fetch strictly before this UTC day",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--min-free-gb", type=float, default=5.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--max-symbols", type=int, default=0)
    args = parser.parse_args()
    if not args.allow_public_network:
        raise ArchiveError("--allow-public-network acknowledgement is required")
    symbols = (
        sorted({item.strip().upper() for item in args.symbols.split(",") if item.strip()})
        if args.symbols else symbols_from_h1(args.h1_dir)
    )
    start_ms = _parse_day(args.start)
    as_of_ms = _parse_day(args.as_of_exclusive) - 1 if args.as_of_exclusive else int(time.time() * 1000)
    if as_of_ms <= start_ms:
        raise ArchiveError("--as-of-exclusive must be after --start")
    status = build_archive(
        symbols=symbols,
        out_dir=args.out_dir,
        start_ms=start_ms,
        as_of_ms=as_of_ms,
        min_free_gb=args.min_free_gb,
        sleep_seconds=args.sleep_seconds,
        max_symbols=args.max_symbols,
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not status["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
