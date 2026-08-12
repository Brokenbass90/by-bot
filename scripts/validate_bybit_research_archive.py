#!/usr/bin/env python3
"""Validate the public Bybit funding/listing archive without network access.

An integrity PASS only means that the downloaded current-universe funding files
are reproducible.  It does not call a 137-current-symbol study point-in-time:
closed symbols also need historical OHLCV before survivorship bias is removed.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_bybit_research_archive import _sha256


def validate(root: Path) -> dict[str, Any]:
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    listing = json.loads((root / "listing_intervals.json").read_text(encoding="utf-8"))
    expected = sorted(str(x).upper() for x in listing.get("requested_symbols") or [])
    files = sorted((root / "funding").glob("*.json"))
    errors: list[str] = []
    warnings: list[str] = []
    ratios: list[float] = []
    total_records = 0
    requested_statuses: Counter[str] = Counter()

    if status.get("state") != "complete":
        errors.append(f"archive_state:{status.get('state')}")
    if status.get("private_api_calls") is not False or status.get("orders_or_risk_mutation") is not False:
        errors.append("authority_not_public_read_only")
    if status.get("failed"):
        errors.append(f"download_failures:{len(status['failed'])}")
    if listing.get("payload_sha256") != _sha256(listing.get("provider_snapshot") or {}):
        errors.append("listing_snapshot_hash_mismatch")
    actual = [path.stem.upper() for path in files]
    if actual != expected:
        errors.append("funding_file_set_not_exact")

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = path.stem.upper()
        rows = list(payload.get("records") or [])
        coverage = dict(payload.get("coverage") or {})
        requested_statuses[str((payload.get("instrument") or {}).get("status") or "unknown")] += 1
        if str(payload.get("symbol") or "").upper() != symbol:
            errors.append(f"{symbol}:symbol_mismatch")
        if payload.get("payload_sha256") != _sha256(rows):
            errors.append(f"{symbol}:payload_hash_mismatch")
        times = [int(row.get("funding_time_ms") or 0) for row in rows]
        if not times or times != sorted(times) or len(times) != len(set(times)):
            errors.append(f"{symbol}:timestamps_invalid")
        if times and (times[0] < int(payload.get("requested_start_ms") or 0) or times[-1] > int(payload.get("as_of_ms") or 0)):
            errors.append(f"{symbol}:timestamp_outside_requested_window")
        if int(coverage.get("observations") or -1) != len(rows):
            errors.append(f"{symbol}:coverage_count_mismatch")
        ratio = coverage.get("coverage_vs_upper_bound")
        if ratio is not None:
            ratios.append(float(ratio))
            if float(ratio) < 0.95:
                warnings.append(f"{symbol}:coverage_vs_upper_bound={float(ratio):.6f}")
        total_records += len(rows)

    provider_records = list((listing.get("provider_snapshot") or {}).get("records") or [])
    provider_statuses = Counter(str(row.get("status") or "unknown") for row in provider_records)
    requested_closed = requested_statuses.get("Closed", 0)
    pit_ohlcv_ready = provider_statuses.get("Closed", 0) == 0 or requested_closed > 0
    if provider_statuses.get("Closed", 0) and requested_closed == 0:
        warnings.append(
            "survivorship_bias_unresolved: provider exposes closed contracts but funding/OHLCV universe contains only current requested symbols"
        )

    integrity_pass = not errors
    return {
        "schema_id": "bybit_research_archive_validation_v1",
        "authority": "research_only_no_orders_no_risk_mutation",
        "integrity_pass": integrity_pass,
        "verdict": "INTEGRITY_PASS_PIT_NOT_READY" if integrity_pass and not pit_ohlcv_ready else "PASS" if integrity_pass else "FAIL",
        "capital_authorized": False,
        "requested_symbol_count": len(expected),
        "funding_file_count": len(files),
        "funding_observation_count": total_records,
        "provider_instrument_count": len(provider_records),
        "provider_status_counts": dict(provider_statuses),
        "requested_status_counts": dict(requested_statuses),
        "minimum_coverage_vs_upper_bound": min(ratios) if ratios else None,
        "coverage_warning_count": sum("coverage_vs_upper_bound" in item for item in warnings),
        "pit_ohlcv_survivorship_resolved": pit_ohlcv_ready,
        "errors": errors,
        "warnings": warnings,
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
    return 0 if result["integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
