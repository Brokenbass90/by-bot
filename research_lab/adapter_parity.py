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
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


SCHEMA_ID = "research_live_adapter_parity_v2"
REPORT_SCHEMA_ID = "research_live_adapter_parity_report_v2"
KEY_FIELDS = ("symbol", "bar_ts", "side")
REQUIRED_FIELDS = {
    "schema_id",
    "release_or_promotion_authority",
    "adapter_emitters_default_off",
    "sleeve_id",
    "spec_id",
    "profile_id",
    "profile_hash",
    "symbol",
    "bar_ts",
    "side",
    "signal_id",
    "decision_id",
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
    "fill_id",
    "order_id",
    "fill_lifecycle",
    "fill_ts_ms",
    "fill_finalized_ts_ms",
    "fill_age_ms",
    "fill_finalization_delay_ms",
    "exit_ts_ms",
    "fill_fingerprint",
    "policy_fingerprint",
    "rebase_claim_key",
    "rebase_receipt_id",
    "execution_fingerprint",
    "frozen_decision",
    "final_fill",
    "rebase_policy",
    "rebase_receipt",
    "cost_contract_hash",
    "outcome",
    "net_r",
    "exception",
}
EXACT_FIELDS = (
    "release_or_promotion_authority",
    "adapter_emitters_default_off",
    "sleeve_id",
    "spec_id",
    "profile_id",
    "profile_hash",
    "signal_id",
    "decision_id",
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
    "fill_id",
    "order_id",
    "fill_lifecycle",
    "fill_ts_ms",
    "fill_finalized_ts_ms",
    "fill_age_ms",
    "fill_finalization_delay_ms",
    "exit_ts_ms",
    "fill_fingerprint",
    "policy_fingerprint",
    "rebase_claim_key",
    "rebase_receipt_id",
    "execution_fingerprint",
    "frozen_decision",
    "final_fill",
    "rebase_policy",
    "rebase_receipt",
    "cost_contract_hash",
    "outcome",
)
PRICE_FIELDS = ("entry", "sl", "tp1", "tp2")
HASH_FIELDS = (
    "profile_hash",
    "config_hash",
    "source_hash",
    "data_hash",
    "fill_fingerprint",
    "policy_fingerprint",
    "rebase_receipt_id",
    "execution_fingerprint",
    "cost_contract_hash",
)
RECEIPT_FIELDS = {
    "schema_id",
    "claim_key",
    "decision_id",
    "order_id",
    "fill_id",
    "fill_fingerprint",
    "policy_fingerprint",
    "execution_fingerprint",
    "receipt_id",
}


class LedgerError(ValueError):
    """The input ledger is not comparable evidence."""


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(f"{field} must be a JSON integer")
    return value


def _finite_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LedgerError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise LedgerError(f"{field} must be a finite decimal")
    return result


def _fingerprint(payload: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise LedgerError("noncanonical durable payload") from exc
    return hashlib.sha256(canonical).hexdigest()


def _key(row: dict[str, Any]) -> tuple[str, int, str]:
    symbol = str(row["symbol"] or "").strip().upper()
    side = str(row["side"] or "").strip().lower()
    bar_ts = _strict_int(row["bar_ts"], "bar_ts")
    if not symbol:
        raise LedgerError("symbol must be nonempty")
    if side not in {"long", "short"}:
        raise LedgerError("side must be long or short")
    if bar_ts <= 0:
        raise LedgerError("bar_ts must be positive")
    return symbol, bar_ts, side


def _is_signal(row: dict[str, Any]) -> bool:
    return bool(row.get("signal_id")) and not str(row.get("validator_drop_reason") or "")


def validate_normalized_row(row: dict[str, Any]) -> None:
    """Validate the v2 evidence envelope before it reaches the comparator."""

    if not isinstance(row, dict):
        raise LedgerError("row is not an object")
    missing = sorted(REQUIRED_FIELDS - set(row))
    extra = sorted(set(row) - REQUIRED_FIELDS)
    if missing:
        raise LedgerError(f"missing fields: {','.join(missing)}")
    if extra:
        raise LedgerError(f"unexpected fields: {','.join(extra)}")
    if row.get("schema_id") != SCHEMA_ID:
        raise LedgerError("wrong schema_id")
    if row.get("release_or_promotion_authority") is not False:
        raise LedgerError("row must not grant release or promotion authority")
    if row.get("adapter_emitters_default_off") is not True:
        raise LedgerError("adapter emitter must remain default-off")
    if row.get("exception") not in (None, "", False):
        raise LedgerError(f"swallowed exception: {row.get('exception')}")
    _key(row)

    for field in HASH_FIELDS:
        if re.fullmatch(r"[0-9a-f]{64}", str(row[field] or "")) is None:
            raise LedgerError(f"{field} must be a lowercase SHA-256")
    for field in PRICE_FIELDS + ("tick_size",):
        if _finite_decimal(row[field], field) <= 0:
            raise LedgerError(f"{field} must be positive")
    _finite_decimal(row["net_r"], "net_r")

    decision_id = str(row["decision_id"] or "")
    if re.fullmatch(r"[0-9a-f]{64}", decision_id) is None:
        raise LedgerError("decision_id must be a lowercase SHA-256")
    if row["signal_id"] != decision_id:
        raise LedgerError("signal_id must equal decision_id")
    if row["fill_lifecycle"] != "finalized":
        raise LedgerError("fill_lifecycle must be finalized")

    bar_ts = _strict_int(row["bar_ts"], "bar_ts")
    fill_ts = _strict_int(row["fill_ts_ms"], "fill_ts_ms")
    finalized_ts = _strict_int(row["fill_finalized_ts_ms"], "fill_finalized_ts_ms")
    fill_age = _strict_int(row["fill_age_ms"], "fill_age_ms")
    finalization_delay = _strict_int(
        row["fill_finalization_delay_ms"], "fill_finalization_delay_ms"
    )
    exit_ts = _strict_int(row["exit_ts_ms"], "exit_ts_ms")
    if fill_age != fill_ts - bar_ts or fill_age < 0:
        raise LedgerError("fill_age_ms is inconsistent")
    if finalization_delay != finalized_ts - fill_ts or finalization_delay < 0:
        raise LedgerError("fill_finalization_delay_ms is inconsistent")
    time_stop = row.get("time_stop")
    if not isinstance(time_stop, dict):
        raise LedgerError("time_stop must be an object")
    deadline = _strict_int(time_stop.get("deadline_ms"), "time_stop.deadline_ms")
    if exit_ts < fill_ts or exit_ts > deadline:
        raise LedgerError("exit_ts_ms is outside the accepted-fill lifecycle")

    frozen = row["frozen_decision"]
    final_fill = row["final_fill"]
    policy = row["rebase_policy"]
    receipt = row["rebase_receipt"]
    if not all(isinstance(value, dict) for value in (frozen, final_fill, policy, receipt)):
        raise LedgerError("durable contract fields must be objects")
    if _fingerprint(frozen) != decision_id:
        raise LedgerError("frozen_decision fingerprint mismatch")
    if _fingerprint(final_fill) != row["fill_fingerprint"]:
        raise LedgerError("final_fill fingerprint mismatch")
    if _fingerprint(policy) != row["policy_fingerprint"]:
        raise LedgerError("rebase_policy fingerprint mismatch")

    if set(receipt) != RECEIPT_FIELDS:
        raise LedgerError("rebase_receipt fields mismatch")
    unsigned_receipt = {key: receipt[key] for key in RECEIPT_FIELDS if key != "receipt_id"}
    if _fingerprint(unsigned_receipt) != receipt["receipt_id"]:
        raise LedgerError("rebase_receipt checksum mismatch")
    receipt_links = {
        "claim_key": row["rebase_claim_key"],
        "decision_id": row["decision_id"],
        "order_id": row["order_id"],
        "fill_id": row["fill_id"],
        "fill_fingerprint": row["fill_fingerprint"],
        "policy_fingerprint": row["policy_fingerprint"],
        "execution_fingerprint": row["execution_fingerprint"],
        "receipt_id": row["rebase_receipt_id"],
    }
    if any(receipt[field] != value for field, value in receipt_links.items()):
        raise LedgerError("rebase_receipt linkage mismatch")

    if frozen.get("config_hash") != row["config_hash"]:
        raise LedgerError("config_hash does not match frozen_decision")
    if frozen.get("source_hash") != row["source_hash"]:
        raise LedgerError("source_hash does not match frozen_decision")
    if frozen.get("data_hash") != row["data_hash"]:
        raise LedgerError("data_hash does not match frozen_decision")
    if frozen.get("profile_hash") != row["profile_hash"]:
        raise LedgerError("profile_hash does not match frozen_decision")
    if final_fill.get("decision_id") != row["decision_id"]:
        raise LedgerError("final_fill decision linkage mismatch")
    if final_fill.get("fill_id") != row["fill_id"] or final_fill.get("order_id") != row["order_id"]:
        raise LedgerError("final_fill identity mismatch")
    if policy.get("spec_id") != row["spec_id"] or policy.get("profile_hash") != row["profile_hash"]:
        raise LedgerError("rebase_policy decision linkage mismatch")


def read_jsonl(path: Path) -> dict[tuple[str, int, str], dict[str, Any]]:
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
        try:
            validate_normalized_row(row)
            key = _key(row)
        except LedgerError as exc:
            raise LedgerError(f"{path}:{line_no}: {exc}") from exc
        if key in rows:
            raise LedgerError(f"{path}:{line_no}: duplicate evaluation key: {key}")
        rows[key] = row
    if not rows:
        raise LedgerError(f"empty ledger: {path}")
    return rows


# Backward-compatible private name for callers that imported the old helper.
_read_jsonl = read_jsonl


def _same_number(left: Any, right: Any, tolerance: Decimal | float | int | str) -> bool:
    if left is None or right is None:
        return left is right
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        allowed = Decimal(str(tolerance))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return (
        a.is_finite()
        and b.is_finite()
        and allowed.is_finite()
        and allowed >= 0
        and abs(a - b) <= allowed
    )


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
            tick = max(Decimal(str(left["tick_size"])), Decimal(str(right["tick_size"])))
        except (InvalidOperation, TypeError, ValueError):
            tick = Decimal("-1")
        if not tick.is_finite() or tick <= 0:
            _append_mismatch(mismatches, key, "tick_size", left["tick_size"], right["tick_size"])
            tick = Decimal("0")
        elif not _same_number(left["tick_size"], right["tick_size"], Decimal("0")):
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
        "schema_id": REPORT_SCHEMA_ID,
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
        report = compare_ledgers(read_jsonl(args.research), read_jsonl(args.live))
    except LedgerError as exc:
        report = {
            "schema_id": REPORT_SCHEMA_ID,
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
