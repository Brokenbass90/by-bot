#!/usr/bin/env python3
"""Resumable, read-only XAU_USD M5 materializer for OANDA v20 candles.

The script has no broker-order capability.  It refuses to decode the reserved
2025-10-01..2026-06-30 holdout, writes every page atomically, never persists or
prints the bearer token, and only creates a consolidated bundle after all page
receipts validate.
"""
from __future__ import annotations

import argparse
import csv
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

from scripts.fetch_forex_oanda import _fetch_chunk, _parse_oanda_ts


SEALED_START = dt.datetime(2025, 10, 1, tzinfo=dt.UTC)
STEP_SECONDS = 5 * 60
SCHEMA_ID = "xau_oanda_m5_preholdout_materialization_v1"
AUTHORITY = "read_only_market_data_no_orders_no_risk_or_promotion"


def _parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_page(path: Path, rows: list[tuple[int, float, float, float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "o", "h", "l", "c", "v"])
        for ts, opened, high, low, closed, volume in rows:
            writer.writerow([ts, f"{opened:.10f}", f"{high:.10f}", f"{low:.10f}", f"{closed:.10f}", f"{volume:.2f}"])
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _rows(payload: dict[str, Any], *, left_ts: int, right_ts: int) -> list[tuple[int, float, float, float, float, float]]:
    rows: list[tuple[int, float, float, float, float, float]] = []
    seen: set[int] = set()
    for candle in payload.get("candles") or []:
        if not candle.get("complete", False):
            continue
        middle = candle.get("mid") or {}
        if not all(key in middle for key in ("o", "h", "l", "c")):
            continue
        timestamp = _parse_oanda_ts(str(candle.get("time") or ""))
        if timestamp < left_ts or timestamp >= right_ts or timestamp in seen:
            continue
        values = tuple(float(middle[key]) for key in ("o", "h", "l", "c"))
        if timestamp % STEP_SECONDS or min(values) <= 0:
            raise ValueError(f"invalid M5 candle at {timestamp}")
        opened, high, low, closed = values
        if high < max(opened, low, closed) or low > min(opened, high, closed):
            raise ValueError(f"invalid OHLC geometry at {timestamp}")
        seen.add(timestamp)
        rows.append((timestamp, opened, high, low, closed, float(candle.get("volume") or 0.0)))
    rows.sort(key=lambda item: item[0])
    return rows


def _free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / (1024 ** 3)


def _base_status(start: dt.datetime, end: dt.datetime, count: int, base_url: str) -> dict[str, Any]:
    return {
        "schema_id": SCHEMA_ID,
        "authority": AUTHORITY,
        "source": "OANDA v20 instrument candles",
        "source_url": "https://developer.oanda.com/rest-live-v20/pricing-ep/",
        "base_url": base_url.rstrip("/"),
        "instrument": "XAU_USD",
        "granularity": "M5",
        "price_component": "M",
        "from_utc": _iso(start),
        "to_utc_exclusive": _iso(end),
        "count_per_request": count,
        "next_from_utc": _iso(start),
        "pages": [],
        "rows": 0,
        "state": "ready",
        "sealed_holdout_rows_decoded": 0,
        "bearer_token_persisted": False,
        "capital_authorized": False,
        "promotion_eligible": False,
    }


def _validate_contract(status: dict[str, Any], expected: dict[str, Any]) -> None:
    keys = ("schema_id", "base_url", "instrument", "granularity", "from_utc", "to_utc_exclusive", "count_per_request")
    mismatched = [key for key in keys if status.get(key) != expected.get(key)]
    if mismatched:
        raise ValueError(f"resume contract mismatch: {','.join(mismatched)}")


def _consolidate(out_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    output = out_dir / "XAUUSD_M5.csv"
    temporary = output.with_suffix(".csv.tmp")
    last_ts: int | None = None
    rows = 0
    with temporary.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(["ts", "o", "h", "l", "c", "v"])
        for page in status["pages"]:
            page_path = out_dir / page["path"]
            if not page_path.is_file() or _sha256(page_path) != page["sha256"]:
                raise ValueError(f"page receipt mismatch: {page['path']}")
            with page_path.open("r", newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    timestamp = int(row["ts"])
                    if last_ts is not None and timestamp <= last_ts:
                        raise ValueError("page order is not strictly increasing")
                    writer.writerow([row[key] for key in ("ts", "o", "h", "l", "c", "v")])
                    last_ts = timestamp
                    rows += 1
        target.flush()
        os.fsync(target.fileno())
    temporary.replace(output)
    return {"path": output.name, "sha256": _sha256(output), "bytes": output.stat().st_size, "rows": rows}


def materialize(
    args: argparse.Namespace,
    *,
    fetch_page: Callable[..., dict[str, Any]] = _fetch_chunk,
) -> int:
    start = _parse_utc(args.from_utc)
    end = _parse_utc(args.to_utc)
    if start >= end:
        raise ValueError("from must precede to")
    if end > SEALED_START:
        raise ValueError("requested range touches sealed holdout")
    count = int(args.count_per_request)
    if count < 1 or count > 5000:
        raise ValueError("count-per-request must be between 1 and 5000")
    base_url = str(args.base_url).rstrip("/")
    expected = _base_status(start, end, count, base_url)

    if args.preflight_only:
        print(json.dumps({**expected, "state": "preflight_pass"}, indent=2, sort_keys=True))
        return 0

    token = str(args.token or "").strip()
    if not token or "YOUR_" in token.upper() or token.upper() in {"TOKEN", "API_TOKEN"}:
        raise ValueError("valid OANDA bearer token required")

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        _validate_contract(status, expected)
    else:
        status = expected
        _atomic_json(status_path, status)

    for page in status.get("pages") or []:
        page_path = out_dir / page["path"]
        if not page_path.is_file() or _sha256(page_path) != page.get("sha256"):
            raise ValueError(f"existing page receipt mismatch: {page.get('path')}")

    cursor = _parse_utc(status["next_from_utc"])
    max_pages = max(0, int(args.max_pages))
    pages_this_run = 0
    while cursor < end:
        if _free_gb(out_dir) < float(args.min_free_gb):
            status.update({"state": "storage_guard", "last_error": "minimum free disk guard reached"})
            _atomic_json(status_path, status)
            return 5
        if max_pages and pages_this_run >= max_pages:
            status["state"] = "paused_budget"
            _atomic_json(status_path, status)
            return 3
        status.update({"state": "fetching", "current_from_utc": _iso(cursor), "last_error": None})
        _atomic_json(status_path, status)
        try:
            payload = fetch_page(
                base_url=base_url,
                token=token,
                instrument="XAU_USD",
                frm=cursor,
                granularity="M5",
                count=count,
            )
            page_rows = _rows(payload, left_ts=int(cursor.timestamp()), right_ts=int(end.timestamp()))
        except Exception as exc:
            status.update({"state": "fetch_error", "last_error": f"{type(exc).__name__}: {exc}"})
            _atomic_json(status_path, status)
            return 4

        if not page_rows:
            status["next_from_utc"] = _iso(end)
            break
        page_number = len(status["pages"]) + 1
        page_path = out_dir / "pages" / f"page_{page_number:06d}.csv"
        _write_page(page_path, page_rows)
        next_cursor = dt.datetime.fromtimestamp(page_rows[-1][0] + STEP_SECONDS, tz=dt.UTC)
        receipt = {
            "path": page_path.relative_to(out_dir).as_posix(),
            "sha256": _sha256(page_path),
            "bytes": page_path.stat().st_size,
            "rows": len(page_rows),
            "first_ts": page_rows[0][0],
            "last_ts": page_rows[-1][0],
        }
        status["pages"].append(receipt)
        status["rows"] = sum(int(item["rows"]) for item in status["pages"])
        status["next_from_utc"] = _iso(min(next_cursor, end))
        _atomic_json(status_path, status)
        cursor = next_cursor
        pages_this_run += 1
        time.sleep(max(0.0, float(args.sleep_sec)))

    status["bundle"] = _consolidate(out_dir, status)
    status.update({"state": "complete_requires_independent_validation", "next_from_utc": _iso(end), "last_error": None})
    _atomic_json(status_path, status)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-utc", default="2021-01-01")
    parser.add_argument("--to-utc", default="2025-10-01")
    parser.add_argument("--out-dir", default="research_lab/data/xauusd_oanda_m5_preholdout_20210101_20250930")
    parser.add_argument("--base-url", default=os.getenv("OANDA_API_URL", "https://api-fxpractice.oanda.com"))
    parser.add_argument("--token", default=os.getenv("OANDA_API_TOKEN", ""))
    parser.add_argument("--count-per-request", type=int, default=5000)
    parser.add_argument("--sleep-sec", type=float, default=0.12)
    parser.add_argument("--min-free-gb", type=float, default=10.0)
    parser.add_argument("--max-pages", type=int, default=0, help="Zero means unlimited; positive values create a resumable budget pause.")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(materialize(parse_args()))
