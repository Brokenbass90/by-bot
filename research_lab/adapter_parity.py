#!/usr/bin/env python3
"""Fail-closed comparison of research and live-adapter decision ledgers.

The comparator deliberately has no trading imports and no credential access.  It
only compares two normalized JSONL ledgers produced from the same immutable data
bytes.  A zero exit code means exact contract parity within exchange-tick
tolerance; any missing field, swallowed exception, unexplained row, geometry or
outcome mismatch exits non-zero and writes a machine-readable report.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


SCHEMA_ID = "research_live_adapter_parity_v1"
KEY_FIELDS = ("symbol", "bar_ts", "side")
REQUIRED_FIELDS = {
    "schema_id",
    "symbol",
    "bar_ts",
    "side",
    "signal_id",
    "entry",
    "sl",
    "tp1",
    "tp2",
    "tp_fracs",
    "runner_fraction",
    "time_stop",
    "cooldown_state",
    "regime_value",
    "regime_bar_ts",
    "validator_drop_reason",
    "config_hash",
    "source_hash",
    "data_hash",
    "tick_size",
    "outcome",
    "net_r",
    "exception",
}
EXACT_FIELDS = (
    "signal_id",
    "tp_fracs",
    "runner_fraction",
    "time_stop",
    "cooldown_state",
    "regime_value",
    "regime_bar_ts",
    "validator_drop_reason",
    "config_hash",
    "source_hash",
    "data_hash",
    "outcome",
)
PRICE_FIELDS = ("entry", "sl", "tp1", "tp2")


class LedgerError(ValueError):
    """The input ledger is not comparable evidence."""


def _key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row["symbol"]).upper(),
        int(row["bar_ts"]),
        str(row["side"]).lower(),
    )


def _is_signal(row: dict[str, Any]) -> bool:
    return bool(row.get("signal_id")) and not str(row.get("validator_drop_reason") or "")


def _read_jsonl(path: Path) -> dict[tuple[str, int, str], dict[str, Any]]:
    if not path.is_file():
        raise LedgerError(f"missing ledger: {path}")
    rows: dict[tuple[str, int, str], dict[str, Any]] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{line_no}: invalid json: {exc}") from exc
        if not isinstance(row, dict):
            raise LedgerError(f"{path}:{line_no}: row is not an object")
        missing = sorted(REQUIRED_FIELDS - set(row))
        if missing:
            raise LedgerError(f"{path}:{line_no}: missing fields: {','.join(missing)}")
        if row.get("schema_id") != SCHEMA_ID:
            raise LedgerError(f"{path}:{line_no}: wrong schema_id")
        if row.get("exception") not in (None, "", False):
            raise LedgerError(f"{path}:{line_no}: swallowed exception: {row.get('exception')}")
        key = _key(row)
        if key in rows:
            raise LedgerError(f"{path}:{line_no}: duplicate evaluation key: {key}")
        rows[key] = row
    if not rows:
        raise LedgerError(f"empty ledger: {path}")
    return rows


def _same_number(left: Any, right: Any, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tolerance


def _append_mismatch(
    mismatches: list[dict[str, Any]],
    key: tuple[str, int, str],
    field: str,
    left: Any,
    right: Any,
) -> None:
    mismatches.append(
        {
            "key": {"symbol": key[0], "bar_ts": key[1], "side": key[2]},
            "field": field,
            "research": left,
            "live": right,
        }
    )


def compare_ledgers(
    research_rows: dict[tuple[str, int, str], dict[str, Any]],
    live_rows: dict[tuple[str, int, str], dict[str, Any]],
) -> dict[str, Any]:
    research_keys, live_keys = set(research_rows), set(live_rows)
    matched = sorted(research_keys & live_keys)
    research_only = sorted(research_keys - live_keys)
    live_only = sorted(live_keys - research_keys)
    denominator = max(len(research_keys), len(live_keys), 1)
    matched_coverage = len(matched) / denominator

    research_signal_count = sum(_is_signal(row) for row in research_rows.values())
    live_signal_count = sum(_is_signal(row) for row in live_rows.values())
    signal_denominator = max(research_signal_count, live_signal_count, 1)
    raw_signal_count_difference = abs(research_signal_count - live_signal_count) / signal_denominator

    mismatches: list[dict[str, Any]] = []
    for key in matched:
        left, right = research_rows[key], live_rows[key]
        try:
            tick = max(float(left["tick_size"]), float(right["tick_size"]))
        except (TypeError, ValueError):
            tick = -1.0
        if not math.isfinite(tick) or tick <= 0:
            _append_mismatch(mismatches, key, "tick_size", left["tick_size"], right["tick_size"])
            tick = 0.0
        elif not _same_number(left["tick_size"], right["tick_size"], 0.0):
            _append_mismatch(mismatches, key, "tick_size", left["tick_size"], right["tick_size"])

        for field in PRICE_FIELDS:
            if not _same_number(left[field], right[field], tick):
                _append_mismatch(mismatches, key, field, left[field], right[field])
        for field in EXACT_FIELDS:
            if left[field] != right[field]:
                _append_mismatch(mismatches, key, field, left[field], right[field])
        if not _same_number(left["net_r"], right["net_r"], 1e-12):
            _append_mismatch(mismatches, key, "net_r", left["net_r"], right["net_r"])

    failures: list[str] = []
    if research_only or live_only:
        failures.append("unmatched_evaluation_rows")
    if matched_coverage < 0.99:
        failures.append("matched_coverage_below_99pct")
    if raw_signal_count_difference > 0.10:
        failures.append("raw_signal_count_difference_above_10pct")
    if mismatches:
        failures.append("contract_field_mismatch")

    def _keys(items: Iterable[tuple[str, int, str]]) -> list[dict[str, Any]]:
        return [{"symbol": x[0], "bar_ts": x[1], "side": x[2]} for x in items]

    return {
        "schema_id": "research_live_adapter_parity_report_v1",
        "decision": "PASS" if not failures else "FAIL_CLOSED",
        "release_or_promotion_authority": False,
        "research_rows": len(research_rows),
        "live_rows": len(live_rows),
        "matched_rows": len(matched),
        "matched_coverage": matched_coverage,
        "research_signal_count": research_signal_count,
        "live_signal_count": live_signal_count,
        "raw_signal_count_difference": raw_signal_count_difference,
        "failures": failures,
        "research_only": _keys(research_only),
        "live_only": _keys(live_only),
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = compare_ledgers(_read_jsonl(args.research), _read_jsonl(args.live))
    except LedgerError as exc:
        report = {
            "schema_id": "research_live_adapter_parity_report_v1",
            "decision": "FAIL_CLOSED",
            "release_or_promotion_authority": False,
            "failures": ["invalid_input_ledger"],
            "error": str(exc),
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("decision") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
