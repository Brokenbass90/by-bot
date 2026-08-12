#!/usr/bin/env python3
"""Validate the research-only Alpaca/Massive daily candidate archive.

The validator is deliberately narrower than a claim of a full historical PIT
universe.  It proves integrity and daily membership intervals *within the
selected candidate pool*.  Current-liquidity selection and incomplete provider
history remain explicit promotion blockers.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "research_lab/data/alpaca_pit_daily_v1"
DEFAULT_RECEIPT = ROOT / "reports/evidence/ALPACA_PIT_DAILY_VALIDATION_20260812.json"


def canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected object")
    return payload


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def date_from_ms(value: int) -> dt.date:
    return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).date()


def validate_archive(archive: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status = read_json(archive / "status.json")
    universe = read_json(archive / "universe.json")
    symbols = [str(x).upper() for x in universe.get("symbols") or []]
    ref = {str(row.get("ticker") or "").upper(): row for row in universe.get("reference") or []}
    errors: list[str] = []
    warnings: list[str] = []
    intervals: list[dict[str, Any]] = []

    if status.get("state") != "complete":
        errors.append(f"materialization_not_complete:{status.get('state')}")
    if len(symbols) != len(set(symbols)):
        errors.append("duplicate_universe_symbols")
    if int(status.get("requested") or 0) != len(symbols):
        errors.append("requested_universe_count_mismatch")
    if status.get("failed"):
        errors.append(f"failed_symbols:{len(status['failed'])}")

    missing = []
    empty = 0
    bars_after_delist = 0
    for symbol in symbols:
        path = archive / "bars" / f"{symbol}.json"
        if not path.exists():
            missing.append(symbol)
            continue
        try:
            payload = read_json(path)
            rows = payload.get("records") or []
            if payload.get("symbol") != symbol:
                errors.append(f"{symbol}:symbol_mismatch")
            if payload.get("adjusted") is not True:
                errors.append(f"{symbol}:not_adjusted")
            if payload.get("payload_sha256") != canonical_sha(rows):
                errors.append(f"{symbol}:sha256_mismatch")
            times = [int(row.get("t") or 0) for row in rows]
            if times != sorted(times) or len(times) != len(set(times)) or any(t <= 0 for t in times):
                errors.append(f"{symbol}:timestamps_invalid")
                continue
            if not times:
                empty += 1
                warnings.append(f"{symbol}:no_daily_bars")
                continue
            first = date_from_ms(times[0])
            last = date_from_ms(times[-1])
            row = ref.get(symbol, {})
            delisted_text = str(row.get("delisted_utc") or "")[:10]
            delisted = dt.date.fromisoformat(delisted_text) if delisted_text else None
            if delisted and last > delisted:
                bars_after_delist += 1
                errors.append(f"{symbol}:bar_after_delist:{last}>{delisted}")
            intervals.append({
                "symbol": symbol,
                "observed_from": first.isoformat(),
                "observed_through": last.isoformat(),
                "delisted_utc": delisted.isoformat() if delisted else None,
                "provider_active": row.get("active"),
                "membership_rule": "daily_bar_exists_and_not_after_delisted_utc",
                "bars": len(times),
            })
        except Exception as exc:
            errors.append(f"{symbol}:{type(exc).__name__}:{exc}")

    if missing:
        errors.append(f"missing_bar_files:{len(missing)}")
    integrity_pass = not errors
    receipt = {
        "schema_id": "alpaca_pit_daily_validation_v1",
        "authority": "research_only_no_orders_no_risk_mutation",
        "capital_authorized": False,
        "archive_state": status.get("state"),
        "requested_symbols": len(symbols),
        "validated_symbols": len(intervals),
        "missing_symbols": missing,
        "empty_symbols": empty,
        "bars_after_delist": bars_after_delist,
        "integrity_pass": integrity_pass,
        "point_in_time_membership_within_selected_pool": integrity_pass,
        "full_market_point_in_time_universe": False,
        "selection_bias_resolved": False,
        "promotion_authorized": False,
        "verdict": "INTEGRITY_PASS_POOL_PIT_ONLY" if integrity_pass else "FAIL_CLOSED",
        "errors": errors,
        "warnings": warnings + [
            "active side selected using current recent liquidity",
            "provider plan exposes only a bounded recent history",
            "membership intervals do not reconstruct every historical US listing",
        ],
    }
    manifest = {
        "schema_id": "alpaca_candidate_pool_membership_intervals_v1",
        "semantics": "PIT intervals within selected pool; not a complete historical market universe",
        "source_universe_sha256": canonical_sha(universe),
        "intervals": intervals,
        "payload_sha256": canonical_sha(intervals),
    }
    return receipt, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    receipt, manifest = validate_archive(args.archive.resolve())
    atomic_json(args.archive.resolve() / "membership_intervals.json", manifest)
    atomic_json(args.receipt.resolve(), receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["integrity_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
