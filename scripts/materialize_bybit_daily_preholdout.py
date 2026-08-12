#!/usr/bin/env python3
"""Build a physically isolated public Bybit daily OHLC archive before holdout.

No credentials, broker endpoints, order paths or risk controls are available.
The end boundary is exclusive and defaults to 2025-10-01 UTC so no bar from the
sealed 2025-10..2026-06 interval is requested or written.
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

from scripts.materialize_public_market_inputs import BYBIT_BASE, _bybit_result, _public_get_json


DEFAULT_OUT = ROOT / "research_lab/data/bybit_daily_preholdout_2023_20250930"
AUTHORITY = "research_only_public_data_no_orders"


class DailyArchiveError(RuntimeError):
    pass


def canonical_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def day_ms(value: str) -> int:
    return int(dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def symbols_from_h1(directory: Path) -> list[str]:
    symbols = sorted({path.stem.upper() for path in directory.glob("*.npz")})
    if not symbols:
        raise DailyArchiveError(f"no symbol filenames in {directory}")
    return symbols


def fetch_daily(
    symbol: str,
    *,
    start_ms: int,
    end_exclusive_ms: int,
    category: str = "linear",
    get_json: Callable[[str, dict[str, Any]], dict[str, Any]] = _public_get_json,
) -> list[dict[str, Any]]:
    if category not in {"linear", "spot"}:
        raise DailyArchiveError(f"unsupported category: {category}")
    out: dict[int, dict[str, Any]] = {}
    cursor_end = end_exclusive_ms - 1
    for _ in range(20):
        payload = get_json(f"{BYBIT_BASE}/v5/market/kline", {
            "category": category, "symbol": symbol, "interval": "D",
            "start": start_ms, "end": cursor_end, "limit": 1000,
        })
        result = _bybit_result(payload, f"Bybit daily {symbol}")
        rows = result.get("list") or []
        if not isinstance(rows, list):
            raise DailyArchiveError(f"{symbol}: malformed daily list")
        if not rows:
            break
        page_times = []
        for row in rows:
            try:
                ts = int(row[0])
                item = {
                    "ts_ms": ts, "open": float(row[1]), "high": float(row[2]),
                    "low": float(row[3]), "close": float(row[4]),
                    "volume": float(row[5]), "turnover": float(row[6]),
                }
            except (IndexError, TypeError, ValueError) as exc:
                raise DailyArchiveError(f"{symbol}: malformed daily row") from exc
            page_times.append(ts)
            if start_ms <= ts < end_exclusive_ms:
                if not (
                    item["open"] > 0 and item["high"] >= max(item["open"], item["close"])
                    and item["low"] <= min(item["open"], item["close"])
                    and item["low"] > 0
                ):
                    raise DailyArchiveError(f"{symbol}: invalid OHLC at {ts}")
                prior = out.get(ts)
                if prior is not None and prior != item:
                    raise DailyArchiveError(f"{symbol}: conflicting duplicate at {ts}")
                out[ts] = item
        oldest = min(page_times)
        if oldest <= start_ms:
            break
        next_end = oldest - 1
        if next_end >= cursor_end:
            raise DailyArchiveError(f"{symbol}: pagination stalled")
        cursor_end = next_end
    else:
        raise DailyArchiveError(f"{symbol}: pagination did not terminate")
    return [out[ts] for ts in sorted(out)]


def materialize(
    symbols: list[str], *, out_dir: Path, start_ms: int, end_exclusive_ms: int,
    min_free_gb: float, sleep_seconds: float, category: str = "linear",
    get_json: Callable[[str, dict[str, Any]], dict[str, Any]] = _public_get_json,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {
        "schema_id": "bybit_daily_preholdout_status_v1", "authority": AUTHORITY,
        "private_api_calls": False, "orders_or_risk_mutation": False,
        "sealed_holdout_rows_decoded": 0, "start_ms": start_ms,
        "end_exclusive_ms": end_exclusive_ms, "requested": len(symbols),
        "category": category,
        "completed": [], "skipped": [], "failed": {}, "state": "running",
    }
    bars_dir = out_dir / "bars"
    bars_dir.mkdir(exist_ok=True)
    for symbol in symbols:
        if shutil.disk_usage(out_dir).free < min_free_gb * 1024**3:
            status["state"] = "stopped_disk_guard"
            atomic_json(out_dir / "status.json", status)
            raise DailyArchiveError("disk guard active")
        path = bars_dir / f"{symbol}.json"
        if path.exists():
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
                rows = prior.get("records") or []
                if (
                    prior.get("payload_sha256") == canonical_sha(rows)
                    and prior.get("end_exclusive_ms") == end_exclusive_ms
                    and prior.get("category", "linear") == category
                ):
                    status["skipped"].append(symbol)
                    continue
            except Exception:
                pass
        try:
            rows = fetch_daily(
                symbol, start_ms=start_ms, end_exclusive_ms=end_exclusive_ms,
                category=category, get_json=get_json,
            )
            payload = {
                "schema_id": "bybit_public_daily_symbol_v1", "authority": AUTHORITY,
                "symbol": symbol, "start_ms": start_ms,
                "end_exclusive_ms": end_exclusive_ms, "interval": "D",
                "category": category,
                "records": rows, "payload_sha256": canonical_sha(rows),
            }
            atomic_json(path, payload)
            status["completed"].append(symbol)
        except Exception as exc:
            status["failed"][symbol] = f"{type(exc).__name__}: {exc}"
        status["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        atomic_json(out_dir / "status.json", status)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    status["state"] = "complete"
    status.update({
        "completed_count": len(status["completed"]), "skipped_count": len(status["skipped"]),
        "failed_count": len(status["failed"]),
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    atomic_json(out_dir / "status.json", status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--h1-dir", type=Path, default=ROOT / "research_lab/data/h1")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end-exclusive", default="2025-10-01")
    parser.add_argument("--min-free-gb", type=float, default=50.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--category", choices=("linear", "spot"), default="linear")
    args = parser.parse_args()
    if not args.allow_public_network:
        raise DailyArchiveError("--allow-public-network acknowledgement required")
    status = materialize(
        symbols_from_h1(args.h1_dir), out_dir=args.out_dir,
        start_ms=day_ms(args.start), end_exclusive_ms=day_ms(args.end_exclusive),
        min_free_gb=args.min_free_gb, sleep_seconds=args.sleep_seconds,
        category=args.category,
    )
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if not status["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
