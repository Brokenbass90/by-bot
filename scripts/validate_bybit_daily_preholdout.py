#!/usr/bin/env python3
"""Independently validate a Bybit daily pre-holdout archive."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_bybit_daily_preholdout import AUTHORITY, canonical_sha


def validate(root: Path) -> dict:
    errors: list[str] = []
    status_path = root / "status.json"
    if not status_path.is_file():
        return {"schema_id": "bybit_daily_preholdout_audit_v1", "verdict": "FAIL", "errors": ["missing_status"]}
    status = json.loads(status_path.read_text(encoding="utf-8"))
    completed = list(status.get("completed") or [])
    failed = dict(status.get("failed") or {})
    category = status.get("category", "linear")
    if status.get("state") != "complete":
        errors.append("status_not_complete")
    if status.get("authority") != AUTHORITY:
        errors.append("authority")
    if status.get("private_api_calls") is not False or status.get("orders_or_risk_mutation") is not False:
        errors.append("authority_flags")
    if int(status.get("sealed_holdout_rows_decoded", -1)) != 0:
        errors.append("holdout_decode_count")
    if len(completed) + len(failed) + len(status.get("skipped") or []) != int(status.get("requested") or -1):
        errors.append("status_count_sum")
    total_rows = 0
    nonempty = 0
    empty: list[str] = []
    for symbol in completed:
        path = root / "bars" / f"{symbol}.json"
        if not path.is_file():
            errors.append(f"missing:{symbol}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = list(payload.get("records") or [])
        if payload.get("symbol") != symbol or payload.get("category", "linear") != category:
            errors.append(f"contract:{symbol}")
        if payload.get("payload_sha256") != canonical_sha(rows):
            errors.append(f"hash:{symbol}")
        timestamps = [int(row.get("ts_ms") or 0) for row in rows]
        if timestamps != sorted(set(timestamps)):
            errors.append(f"timestamps:{symbol}")
        start = int(status.get("start_ms") or 0)
        end = int(status.get("end_exclusive_ms") or 0)
        if any(not start <= ts < end for ts in timestamps):
            errors.append(f"range:{symbol}")
        total_rows += len(rows)
        if rows:
            nonempty += 1
        else:
            empty.append(symbol)
    unsupported = sorted(failed)
    integrity = not errors
    if not integrity:
        verdict = "FAIL"
    elif unsupported or empty:
        verdict = "INTEGRITY_PASS_PARTIAL_MARKET_COVERAGE"
    else:
        verdict = "PASS"
    return {
        "schema_id": "bybit_daily_preholdout_audit_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "authority": "independent_read_only_validation",
        "category": category,
        "requested_symbols": int(status.get("requested") or 0),
        "completed_symbols": len(completed),
        "nonempty_symbols": nonempty,
        "empty_symbols": empty,
        "unsupported_symbols": unsupported,
        "total_rows": total_rows,
        "sealed_holdout_rows_decoded": 0,
        "pit_universe_ready": False,
        "promotion_authorized": False,
        "errors": sorted(set(errors)),
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = validate(args.root)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 2 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
