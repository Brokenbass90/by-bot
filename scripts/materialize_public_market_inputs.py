#!/usr/bin/env python3
"""Materialize public PIT instruments and cross-exchange funding history.

Research-only:
* public GET requests only;
* no credentials or environment reads;
* no broker calls, orders, transfers, or capital;
* atomic outputs with a deterministic payload hash.

The Bybit universe intentionally queries every documented linear status,
including ``Closed``.  That makes delisted contracts visible instead of
silently building a survivor-only universe from today's trading symbols.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
BYBIT_BASE = "https://api.bybit.com"
BITGET_BASE = "https://api.bitget.com"
MEXC_BASE = "https://contract.mexc.com"
# The live linear endpoint currently accepts these three values.  Although the
# generic API explorer also enumerates Settling/Delivering, Bybit returns
# retCode=10001 for those values on category=linear (verified 2026-07-25).
BYBIT_STATUSES = ("PreLaunch", "Trading", "Closed")
DEFAULT_SYMBOLS = (
    "ADAUSDT",
    "BTCUSDT",
    "DOTUSDT",
    "ETHUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "SOLUSDT",
    "SUIUSDT",
)
JsonGetter = Callable[[str, dict[str, Any]], dict[str, Any]]


class MaterializationError(RuntimeError):
    """Fail-closed public input materialization error."""


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _public_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": "by-bot-public-research/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=25.0) as response:
                value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise MaterializationError("public endpoint returned non-object JSON")
            return value
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.5 * (2**attempt))
    raise MaterializationError(f"public GET retries exhausted: {last_error}")


def _bybit_result(payload: dict[str, Any], label: str) -> dict[str, Any]:
    if int(payload.get("retCode", -1)) != 0:
        raise MaterializationError(
            f"{label}: Bybit retCode={payload.get('retCode')} retMsg={payload.get('retMsg')}"
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise MaterializationError(f"{label}: missing Bybit result object")
    return result


def _bitget_rows(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    if str(payload.get("code") or "") != "00000":
        raise MaterializationError(
            f"{label}: Bitget code={payload.get('code')} msg={payload.get('msg')}"
        )
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MaterializationError(f"{label}: missing Bitget data list")
    if not all(isinstance(row, dict) for row in rows):
        raise MaterializationError(f"{label}: malformed Bitget row")
    return rows


def _mexc_result(payload: dict[str, Any], label: str) -> dict[str, Any]:
    if payload.get("success") is not True or int(payload.get("code", -1)) != 0:
        raise MaterializationError(
            f"{label}: MEXC success={payload.get('success')} "
            f"code={payload.get('code')} message={payload.get('message')}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MaterializationError(f"{label}: missing MEXC data object")
    return data


def fetch_bybit_linear_universe(
    get_json: JsonGetter = _public_get_json,
    *,
    statuses: Iterable[str] = BYBIT_STATUSES,
) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, Any]] = {}
    status_counts: dict[str, int] = {}
    page_counts: dict[str, int] = {}

    for status in statuses:
        cursor = ""
        seen_cursors: set[str] = set()
        count = 0
        pages = 0
        for _ in range(50):
            params: dict[str, Any] = {
                "category": "linear",
                "status": status,
                "limit": 1000,
            }
            if cursor:
                params["cursor"] = cursor
            payload = get_json(f"{BYBIT_BASE}/v5/market/instruments-info", params)
            result = _bybit_result(payload, f"Bybit instruments status={status}")
            rows = result.get("list") or []
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise MaterializationError(f"Bybit instruments status={status}: malformed list")
            pages += 1
            for row in rows:
                symbol = str(row.get("symbol") or "").upper()
                if not symbol:
                    raise MaterializationError(f"Bybit instruments status={status}: empty symbol")
                declared = str(row.get("status") or "")
                if declared != status:
                    raise MaterializationError(
                        f"Bybit instruments status mismatch: requested={status} row={declared}"
                    )
                previous = by_symbol.get(symbol)
                if previous is not None and _canonical_bytes(previous) != _canonical_bytes(row):
                    raise MaterializationError(f"conflicting duplicate Bybit instrument: {symbol}")
                by_symbol[symbol] = row
                count += 1
            next_cursor = str(result.get("nextPageCursor") or "")
            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise MaterializationError(
                    f"Bybit instruments status={status}: repeated pagination cursor"
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise MaterializationError(
                f"Bybit instruments status={status}: pagination did not terminate"
            )
        status_counts[status] = count
        page_counts[status] = pages

    records = sorted(by_symbol.values(), key=lambda row: str(row.get("symbol") or ""))
    core = {
        "schema_id": "bybit_linear_pit_universe_v1",
        "provider": "bybit",
        "category": "linear",
        "statuses_requested": list(statuses),
        "status_counts": status_counts,
        "page_counts": page_counts,
        "record_count": len(records),
        "records": records,
    }
    return core


def _funding_record(
    *,
    venue: str,
    symbol: str,
    timestamp: Any,
    rate: Any,
) -> dict[str, Any]:
    try:
        ts = int(timestamp)
        parsed_rate = float(rate)
    except (TypeError, ValueError) as exc:
        raise MaterializationError(
            f"{venue} {symbol}: malformed funding timestamp/rate"
        ) from exc
    if ts <= 0 or not math.isfinite(parsed_rate):
        raise MaterializationError(f"{venue} {symbol}: invalid funding timestamp/rate")
    return {
        "venue": venue,
        "symbol": symbol,
        "funding_time_ms": ts,
        "funding_rate": parsed_rate,
    }


def fetch_bybit_funding_history(
    symbol: str,
    *,
    cutoff_ms: int,
    as_of_ms: int,
    get_json: JsonGetter = _public_get_json,
) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    end_ms = as_of_ms
    for _ in range(80):
        payload = get_json(
            f"{BYBIT_BASE}/v5/market/funding/history",
            {
                "category": "linear",
                "symbol": symbol,
                "endTime": end_ms,
                "limit": 200,
            },
        )
        result = _bybit_result(payload, f"Bybit funding {symbol}")
        rows = result.get("list") or []
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise MaterializationError(f"Bybit funding {symbol}: malformed list")
        if not rows:
            break
        page_times: list[int] = []
        for row in rows:
            record = _funding_record(
                venue="bybit",
                symbol=symbol,
                timestamp=row.get("fundingRateTimestamp"),
                rate=row.get("fundingRate"),
            )
            ts = int(record["funding_time_ms"])
            page_times.append(ts)
            if cutoff_ms <= ts <= as_of_ms:
                previous = out.get(ts)
                if previous is not None and previous != record:
                    raise MaterializationError(
                        f"Bybit funding {symbol}: conflicting duplicate at {ts}"
                    )
                out[ts] = record
        oldest = min(page_times)
        if oldest <= cutoff_ms:
            break
        next_end = oldest - 1
        if next_end >= end_ms:
            raise MaterializationError(f"Bybit funding {symbol}: pagination stalled")
        end_ms = next_end
    else:
        raise MaterializationError(f"Bybit funding {symbol}: pagination did not terminate")
    return [out[ts] for ts in sorted(out)]


def fetch_bitget_funding_history(
    symbol: str,
    *,
    cutoff_ms: int,
    as_of_ms: int,
    get_json: JsonGetter = _public_get_json,
) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for page_no in range(1, 101):
        payload = get_json(
            f"{BITGET_BASE}/api/v2/mix/market/history-fund-rate",
            {
                "symbol": symbol,
                "productType": "USDT-FUTURES",
                "pageSize": 100,
                "pageNo": page_no,
            },
        )
        rows = _bitget_rows(payload, f"Bitget funding {symbol} page={page_no}")
        if not rows:
            break
        page_times: list[int] = []
        for row in rows:
            record = _funding_record(
                venue="bitget",
                symbol=symbol,
                timestamp=row.get("fundingTime"),
                rate=row.get("fundingRate"),
            )
            ts = int(record["funding_time_ms"])
            page_times.append(ts)
            if cutoff_ms <= ts <= as_of_ms:
                previous = out.get(ts)
                if previous is not None and previous != record:
                    raise MaterializationError(
                        f"Bitget funding {symbol}: conflicting duplicate at {ts}"
                    )
                out[ts] = record
        if min(page_times) <= cutoff_ms or len(rows) < 100:
            break
    else:
        raise MaterializationError(f"Bitget funding {symbol}: pagination did not terminate")
    return [out[ts] for ts in sorted(out)]


def fetch_mexc_funding_history(
    symbol: str,
    *,
    cutoff_ms: int,
    as_of_ms: int,
    get_json: JsonGetter = _public_get_json,
) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    mexc_symbol = symbol[:-4] + "_USDT" if symbol.endswith("USDT") else symbol
    for page_no in range(1, 101):
        payload = get_json(
            f"{MEXC_BASE}/api/v1/contract/funding_rate/history",
            {
                "symbol": mexc_symbol,
                "page_num": page_no,
                "page_size": 1000,
            },
        )
        data = _mexc_result(payload, f"MEXC funding {symbol} page={page_no}")
        rows = data.get("resultList") or []
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise MaterializationError(f"MEXC funding {symbol}: malformed resultList")
        if not rows:
            break
        page_times: list[int] = []
        for row in rows:
            record = _funding_record(
                venue="mexc",
                symbol=symbol,
                timestamp=row.get("settleTime"),
                rate=row.get("fundingRate"),
            )
            ts = int(record["funding_time_ms"])
            page_times.append(ts)
            if cutoff_ms <= ts <= as_of_ms:
                previous = out.get(ts)
                if previous is not None and previous != record:
                    raise MaterializationError(
                        f"MEXC funding {symbol}: conflicting duplicate at {ts}"
                    )
                out[ts] = record
        total_pages = int(data.get("totalPage") or 0)
        if min(page_times) <= cutoff_ms or page_no >= total_pages:
            break
    else:
        raise MaterializationError(f"MEXC funding {symbol}: pagination did not terminate")
    return [out[ts] for ts in sorted(out)]


def _coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    times = sorted({int(row["funding_time_ms"]) for row in records})
    diffs_h = [
        (right - left) / 3_600_000.0
        for left, right in zip(times, times[1:])
        if right > left
    ]
    return {
        "observation_count": len(times),
        "first_funding_time_ms": times[0] if times else None,
        "last_funding_time_ms": times[-1] if times else None,
        "coverage_days": (
            round((times[-1] - times[0]) / 86_400_000.0, 4)
            if len(times) >= 2
            else 0.0
        ),
        "median_interval_hours": (
            round(float(statistics.median(diffs_h)), 6) if diffs_h else None
        ),
        "max_gap_hours": round(max(diffs_h), 6) if diffs_h else None,
    }


def fetch_cross_exchange_funding(
    symbols: Iterable[str],
    *,
    days: int,
    as_of_ms: int,
    min_observations: int,
    get_json: JsonGetter = _public_get_json,
) -> dict[str, Any]:
    cutoff_ms = as_of_ms - int(days) * 86_400_000
    all_records: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, Any]] = {}
    normalized_symbols = sorted({str(symbol).strip().upper() for symbol in symbols if symbol})
    if not normalized_symbols:
        raise MaterializationError("funding symbol list is empty")

    for symbol in normalized_symbols:
        venue_records = {
            "bybit": fetch_bybit_funding_history(
                symbol,
                cutoff_ms=cutoff_ms,
                as_of_ms=as_of_ms,
                get_json=get_json,
            ),
            "mexc": fetch_mexc_funding_history(
                symbol,
                cutoff_ms=cutoff_ms,
                as_of_ms=as_of_ms,
                get_json=get_json,
            ),
        }
        for venue, records in venue_records.items():
            key = f"{venue}:{symbol}"
            coverage[key] = _coverage(records)
            if len(records) < min_observations:
                raise MaterializationError(
                    f"{key}: only {len(records)} observations, need {min_observations}"
                )
            all_records.extend(records)

    all_records.sort(
        key=lambda row: (
            str(row["symbol"]),
            str(row["venue"]),
            int(row["funding_time_ms"]),
        )
    )
    return {
        "schema_id": "cross_exchange_public_funding_history_v1",
        "venues": ["bybit", "mexc"],
        "symbols": normalized_symbols,
        "requested_days": int(days),
        "cutoff_ms": cutoff_ms,
        "as_of_ms": as_of_ms,
        "min_observations_per_venue_symbol": int(min_observations),
        "coverage_by_venue_symbol": coverage,
        "record_count": len(all_records),
        "records": all_records,
    }


def _envelope(core: dict[str, Any]) -> dict[str, Any]:
    return {
        "research_only": True,
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "materialized_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload_sha256": _sha256(core),
        **core,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize public PIT instruments and funding histories."
    )
    parser.add_argument(
        "mode",
        choices=("universe", "funding", "all"),
        help="Which public input bundle to materialize.",
    )
    parser.add_argument(
        "--allow-public-network",
        action="store_true",
        help="Required acknowledgement for public GET requests.",
    )
    parser.add_argument(
        "--universe-out",
        default="research_lab/data/bybit_instruments_linear.json",
    )
    parser.add_argument(
        "--funding-out",
        default="research_lab/data/cross_exchange_funding_history_180d.json",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
    )
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--min-observations", type=int, default=400)
    args = parser.parse_args()

    if not args.allow_public_network:
        raise MaterializationError("--allow-public-network acknowledgement is required")
    if args.days < 30:
        raise MaterializationError("--days must be at least 30")
    if args.min_observations < 1:
        raise MaterializationError("--min-observations must be positive")

    if args.mode in {"universe", "all"}:
        universe = _envelope(fetch_bybit_linear_universe())
        universe_path = ROOT / args.universe_out
        _atomic_json(universe_path, universe)
        print(
            f"universe records={universe['record_count']} "
            f"statuses={universe['status_counts']} saved={universe_path}"
        )

    if args.mode in {"funding", "all"}:
        as_of_ms = int(time.time() * 1000)
        symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
        funding = _envelope(
            fetch_cross_exchange_funding(
                symbols,
                days=int(args.days),
                as_of_ms=as_of_ms,
                min_observations=int(args.min_observations),
            )
        )
        funding_path = ROOT / args.funding_out
        _atomic_json(funding_path, funding)
        print(
            f"funding records={funding['record_count']} symbols={len(funding['symbols'])} "
            f"saved={funding_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
