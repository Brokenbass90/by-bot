#!/usr/bin/env python3
"""Build one physically isolated public Bybit M5 input before a sealed holdout."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_bybit_daily_preholdout import atomic_json, canonical_sha, day_ms
from scripts.materialize_public_market_inputs import BYBIT_BASE, _bybit_result, _public_get_json

AUTHORITY = "research_only_public_data_no_orders"


def fetch_5m(
    symbol: str, *, start_ms: int, end_exclusive_ms: int,
    get_json: Callable[[str, dict[str, Any]], dict[str, Any]] = _public_get_json,
) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    cursor_end = end_exclusive_ms - 1
    for _ in range(400):
        payload = get_json(f"{BYBIT_BASE}/v5/market/kline", {
            "category": "linear", "symbol": symbol, "interval": "5",
            "start": start_ms, "end": cursor_end, "limit": 1000,
        })
        rows = _bybit_result(payload, f"Bybit M5 {symbol}").get("list") or []
        if not rows:
            break
        page_times: list[int] = []
        for row in rows:
            ts = int(row[0])
            page_times.append(ts)
            if start_ms <= ts < end_exclusive_ms:
                item = {
                    "ts_ms": ts, "open": float(row[1]), "high": float(row[2]),
                    "low": float(row[3]), "close": float(row[4]),
                    "volume": float(row[5]), "turnover": float(row[6]),
                }
                if item["low"] <= 0 or item["high"] < max(item["open"], item["close"]):
                    raise RuntimeError(f"invalid OHLC at {ts}")
                if ts in out and out[ts] != item:
                    raise RuntimeError(f"conflicting duplicate at {ts}")
                out[ts] = item
        oldest = min(page_times)
        if oldest <= start_ms:
            break
        next_end = oldest - 1
        if next_end >= cursor_end:
            raise RuntimeError("pagination stalled")
        cursor_end = next_end
    else:
        raise RuntimeError("pagination did not terminate")
    return [out[ts] for ts in sorted(out)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--start", default="2024-03-01")
    parser.add_argument("--end-exclusive", default="2025-10-01")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-free-gb", type=float, default=50.0)
    args = parser.parse_args()
    if not args.allow_public_network:
        raise RuntimeError("--allow-public-network acknowledgement required")
    if shutil.disk_usage(args.out_dir.parent).free < args.min_free_gb * 1024**3:
        raise RuntimeError("disk guard active")
    start_ms, end_ms = day_ms(args.start), day_ms(args.end_exclusive)
    rows = fetch_5m(args.symbol, start_ms=start_ms, end_exclusive_ms=end_ms)
    payload = {
        "schema_id": "bybit_public_m5_preholdout_v1", "authority": AUTHORITY,
        "symbol": args.symbol, "start_ms": start_ms, "end_exclusive_ms": end_ms,
        "interval": "5", "records": rows, "payload_sha256": canonical_sha(rows),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.out_dir / f"{args.symbol}.json", payload)
    status = {
        "schema_id": "bybit_public_m5_preholdout_status_v1", "authority": AUTHORITY,
        "symbol": args.symbol, "records": len(rows), "start_ms": start_ms,
        "end_exclusive_ms": end_ms, "sealed_holdout_rows_decoded": 0,
        "private_api_calls": False, "orders_or_risk_mutation": False,
        "payload_sha256": payload["payload_sha256"], "state": "complete",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    atomic_json(args.out_dir / "status.json", status)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
