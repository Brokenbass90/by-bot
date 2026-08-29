#!/usr/bin/env python3
"""Read-only forensic audit of the consumed ATT1/SBR1 reserved OOS failure."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CONFIG = Path("configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json")
AUTH = Path("configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json")
CANDIDATE_CONFIG = Path("configs/research/att1_sbr1_live_native_parity_v1.json")
OUTPUT = Path("research_lab/results/att1_sbr1_reserved_oos_v1")
CLAIM = OUTPUT / "one_shot_claim.json"
RECEIPT = OUTPUT / "receipt.json"
WINDOW = {
    "start_utc": "2025-10-01T00:00:00Z",
    "end_utc_exclusive": "2026-07-01T00:00:00Z",
}
ROOT_CAUSE = "AttributeError:'tuple' object has no attribute 'get'"
MAJOR8 = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "DOTUSDT",
    "SUIUSDT",
)
REGIME_VALUES = {"above_band", "below_band", "flat_down", "flat_up"}
BOOTSTRAP_ROWS_PER_SYMBOL = 166_752
BOOTSTRAP_START_TS_MS = 1_709_251_200_000
BOOTSTRAP_END_TS_MS = 1_759_276_500_000
EVALUATION_START_TS_MS = 1_759_280_400_000
EVALUATION_END_TS_MS = 1_782_860_400_000
EVALUATION_STEP_MS = 3_600_000
EVALUATION_ROWS_PER_SYMBOL = 6_551
RESERVED_ACCOUNTING_KEYS = {
    "started_at_utc",
    "finished_at_utc",
    "inputs",
    "inputs_validated",
    "inputs_opened",
    "inputs_decoded",
    "rows_validated",
    "rows_observed",
    "rows",
}
BOOTSTRAP_ACCOUNTING_KEYS = {
    "started_at_utc",
    "finished_at_utc",
    "inputs",
    "rows",
}
RESERVED_INPUT_KEYS = {
    "path",
    "bytes",
    "sha256",
    "rows",
    "start_ts_ms",
    "end_ts_ms",
    "validation_status",
    "validation_error",
    "opened_bytes",
    "opened_sha256",
    "json_decoded",
    "rows_observed",
}
BOOTSTRAP_INPUT_KEYS = {
    "path",
    "bytes",
    "sha256",
    "pinned_sha256",
    "rows",
    "start_ts_ms",
    "end_ts_ms",
    "validation_status",
    "validation_error",
}
EVALUATION_KEYS = {
    "bar_ts",
    "eligible_regime",
    "regime_bar_ts",
    "regime_value",
    "side_contract",
    "sleeve_id",
    "symbol",
    "exception",
    "signal",
}
SIGNAL_KEYS = {
    "strategy",
    "symbol",
    "side",
    "entry",
    "sl",
    "tp",
    "tps",
    "tp_fracs",
    "time_stop_bars",
    "reason",
}
PARITY_REPORT_KEYS = {
    "schema_id",
    "decision",
    "release_or_promotion_authority",
    "research_rows",
    "live_rows",
    "matched_rows",
    "matched_coverage",
    "research_signal_count",
    "live_signal_count",
    "raw_signal_count_difference",
    "failures",
    "research_only",
    "live_only",
    "mismatches",
    "research_ledger_sha256",
    "live_ledger_sha256",
}
FORENSIC_RECEIPT_KEYS = {
    "schema_id",
    "authority",
    "decision",
    "root_cause",
    "receipt_sha256",
    "claim_sha256",
    "identities",
    "economics",
    "money_authority",
    "promotion_authority",
    "forensic_receipt_sha256",
}
IDENTITY_KEYS = {
    "config_sha256",
    "input_manifest_sha256",
    "runner_sha256",
    "audit_sha256",
    "authorization_sha256",
}
THRESHOLD_KEYS = {
    "n_gte",
    "mean_r_gt",
    "profit_factor_gte",
    "both_halves_r_gt",
    "max_sequential_drawdown_r_lte",
    "positive_month_fraction_gte",
    "positive_symbol_concentration_lte",
    "minimum_leave_one_symbol_out_r_gt",
}
EXPECTED_ARTIFACTS = {
    f"{sleeve}_{mode}_{shape}.jsonl"
    for sleeve in ("att1", "sbr1")
    for mode in ("evaluation", "base", "stress")
    for shape in ("research", "live")
} | {
    f"{sleeve}_{mode}_parity_report.json"
    for sleeve in ("att1", "sbr1")
    for mode in ("base", "stress")
}


class FailureAuditViolation(RuntimeError):
    pass


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _has_symlink_component(path: Path) -> bool:
    candidate = path.absolute()
    return any(component.is_symlink() for component in (candidate, *candidate.parents))


def sha256_file(path: Path) -> str:
    if _has_symlink_component(path) or not path.is_file():
        raise FailureAuditViolation(f"missing or unsafe file:{path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _object(path: Path, label: str) -> dict[str, Any]:
    if _has_symlink_component(path) or not path.is_file():
        raise FailureAuditViolation(f"missing or unsafe {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureAuditViolation(f"malformed {label}") from exc
    if not isinstance(value, dict):
        raise FailureAuditViolation(f"malformed {label}")
    return value


def verify_receipt(receipt: Mapping[str, Any]) -> None:
    unsigned = dict(receipt)
    actual = str(unsigned.pop("receipt_sha256", ""))
    if actual != canonical_sha256(unsigned):
        raise FailureAuditViolation("receipt canonical hash drift")
    if (
        receipt.get("schema_id")
        != "att1_sbr1_reserved_oos_one_shot_receipt_v1"
        or receipt.get("terminal_state") != "FAIL_CLOSED_AFTER_CLAIM"
    ):
        raise FailureAuditViolation("terminal failure contract drift")
    if (
        receipt.get("classification")
        != "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION"
        or not receipt.get("terminal_at_utc")
        or not receipt.get("market_decode_started_at_utc")
        or not receipt.get("market_decode_finished_at_utc")
    ):
        raise FailureAuditViolation("terminal forensic fields drift")
    if receipt.get("error") != ROOT_CAUSE:
        raise FailureAuditViolation("failure root cause drift")


def _parse_time(value: object, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise FailureAuditViolation(f"invalid timestamp:{label}") from exc
    if parsed.tzinfo is None:
        raise FailureAuditViolation(f"invalid timestamp:{label}")
    return parsed


def _assert_equal_hashes(rows: Mapping[str, object], output: Path, label: str) -> None:
    if not isinstance(rows, Mapping):
        raise FailureAuditViolation(f"{label} inventory missing")
    for name, digest in rows.items():
        path = output / str(name)
        if sha256_file(path) != digest:
            raise FailureAuditViolation(f"{label} hash drift:{name}")


def _validate_output_inventories(receipt: Mapping[str, Any], output: Path) -> None:
    if _has_symlink_component(output) or not output.is_dir():
        raise FailureAuditViolation("output directory unsafe")
    actual = {path.name for path in output.iterdir()}
    if actual != EXPECTED_ARTIFACTS | {CLAIM.name, RECEIPT.name}:
        raise FailureAuditViolation("actual output inventory drift")
    if any(path.is_symlink() or not path.is_file() for path in output.iterdir()):
        raise FailureAuditViolation("actual output entry unsafe")
    partial = receipt.get("partial_output_file_sha256")
    if not isinstance(partial, Mapping) or set(partial) != EXPECTED_ARTIFACTS:
        raise FailureAuditViolation("partial output inventory drift")
    _assert_equal_hashes(partial, output, "partial output")
    observed = receipt.get("observed_output_entries")
    expected_observed = EXPECTED_ARTIFACTS | {CLAIM.name}
    if not isinstance(observed, list) or len(observed) != len(expected_observed):
        raise FailureAuditViolation("observed inventory drift")
    rows = {str(row.get("name")): row for row in observed if isinstance(row, Mapping)}
    if set(rows) != EXPECTED_ARTIFACTS | {CLAIM.name}:
        raise FailureAuditViolation("observed inventory names drift")
    for name, row in rows.items():
        if (
            row.get("status") != "HASHED"
            or row.get("kind") != "regular_file"
            or row.get("is_regular_file") is not True
            or row.get("is_symlink") is not False
            or row.get("error") is not None
            or row.get("sha256") != sha256_file(output / name)
        ):
            raise FailureAuditViolation(f"observed inventory row drift:{name}")


def _validated_source_pin(
    root: Path,
    config: Mapping[str, Any],
    role: str,
    expected_path: Path,
    error_label: str,
) -> Mapping[str, Any]:
    pins = config.get("source_pins")
    if not isinstance(pins, list):
        raise FailureAuditViolation(error_label)
    matches = [
        row
        for row in pins
        if isinstance(row, Mapping) and row.get("role") == role
    ]
    if len(matches) != 1:
        raise FailureAuditViolation(error_label)
    pin = matches[0]
    if (
        pin.get("path") != expected_path.as_posix()
        or sha256_file(root / expected_path) != pin.get("sha256")
    ):
        raise FailureAuditViolation(error_label)
    return pin


def _validate_accounting(
    root: Path,
    config: Mapping[str, Any],
    accounting: object,
    decode_started_at: object,
    decode_finished_at: object,
) -> None:
    if not isinstance(accounting, Mapping):
        raise FailureAuditViolation("decode accounting drift")
    manifest = _object(
        root / "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json",
        "reserved manifest",
    )
    _validated_source_pin(
        root,
        config,
        "live_native_candidate",
        CANDIDATE_CONFIG,
        "candidate pin drift",
    )
    candidate = _object(root / CANDIDATE_CONFIG, "candidate manifest")
    contracts = {
        "reserved": (628_992, True, manifest["inputs"]),
        "bootstrap": (1_334_016, False, candidate["data_files"]),
    }
    section_times: dict[str, tuple[datetime, datetime]] = {}
    for group, (expected_rows, opened, frozen_rows) in contracts.items():
        section = accounting.get(group)
        expected_section_keys = (
            RESERVED_ACCOUNTING_KEYS
            if group == "reserved"
            else BOOTSTRAP_ACCOUNTING_KEYS
        )
        if (
            not isinstance(section, Mapping)
            or set(section) != expected_section_keys
            or type(section.get("rows")) is not int
            or section["rows"] != expected_rows
            or not isinstance(section.get("inputs"), Mapping)
            or set(section["inputs"]) != set(MAJOR8)
        ):
            raise FailureAuditViolation(f"decode accounting drift:{group}")
        if group == "reserved" and (
            section.get("inputs_validated") != 8
            or section.get("inputs_decoded") != 8
            or section.get("rows_validated") != expected_rows
            or section.get("rows_observed") != expected_rows
            or section.get("inputs_opened") != 8
        ):
            raise FailureAuditViolation("decode accounting drift:reserved")
        frozen = {str(row["symbol"]): row for row in frozen_rows}
        observed_row_sum = 0
        for symbol, row in section["inputs"].items():
            expected_input_keys = (
                RESERVED_INPUT_KEYS
                if group == "reserved"
                else BOOTSTRAP_INPUT_KEYS
            )
            if (
                not isinstance(row, Mapping)
                or set(row) != expected_input_keys
                or row.get("validation_status") != "VALIDATED"
                or row.get("validation_error") is not None
                or type(row.get("rows")) is not int
                or row["rows"] <= 0
                or symbol not in MAJOR8
            ):
                raise FailureAuditViolation(f"decode input drift:{group}:{symbol}")
            expected = frozen[symbol]
            expected_path_key = "source_path" if group == "reserved" else "path"
            if (
                row.get("path") != expected[expected_path_key]
                or row.get("sha256") != expected["sha256"]
                or row.get("bytes") != expected["bytes"]
            ):
                raise FailureAuditViolation(f"decode frozen pin drift:{group}:{symbol}")
            if group == "reserved":
                if (
                    row["rows"] != expected["rows"]
                    or type(row.get("start_ts_ms")) is not int
                    or row["start_ts_ms"] != expected["first_ts_ms"]
                    or type(row.get("end_ts_ms")) is not int
                    or row["end_ts_ms"] != expected["last_ts_ms"]
                    or row.get("json_decoded") is not True
                    or type(row.get("rows_observed")) is not int
                    or row["rows_observed"] != expected["rows"]
                ):
                    raise FailureAuditViolation(f"decode frozen identity drift:{group}:{symbol}")
            elif (
                row["rows"] != BOOTSTRAP_ROWS_PER_SYMBOL
                or type(row.get("start_ts_ms")) is not int
                or row["start_ts_ms"] != BOOTSTRAP_START_TS_MS
                or type(row.get("end_ts_ms")) is not int
                or row["end_ts_ms"] != BOOTSTRAP_END_TS_MS
            ):
                raise FailureAuditViolation(f"decode frozen identity drift:{group}:{symbol}")
            if row.get("sha256") != row.get("pinned_sha256", row.get("sha256")):
                raise FailureAuditViolation(f"decode hash drift:{group}:{symbol}")
            if opened and (
                row.get("opened_sha256") != row.get("sha256")
                or row.get("opened_bytes") != row.get("bytes")
            ):
                raise FailureAuditViolation(f"decode open hash drift:{group}:{symbol}")
            observed_row_sum += row["rows"]
        if observed_row_sum != expected_rows:
            raise FailureAuditViolation(f"decode accounting drift:{group}")
        section_times[group] = (
            _parse_time(section["started_at_utc"], f"{group} accounting start"),
            _parse_time(section["finished_at_utc"], f"{group} accounting finish"),
        )

    decode_start = _parse_time(decode_started_at, "decode start")
    decode_finish = _parse_time(decode_finished_at, "decode finish")
    reserved_start, reserved_finish = section_times["reserved"]
    bootstrap_start, bootstrap_finish = section_times["bootstrap"]
    if not (
        decode_start == reserved_start
        <= reserved_finish
        <= bootstrap_start
        <= bootstrap_finish == decode_finish
    ):
        raise FailureAuditViolation("decode accounting timing drift")


def _validate_auth_claim_receipt(
    auth: Mapping[str, Any],
    claim: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> None:
    auth_exact = {
        "schema_id": "att1_sbr1_reserved_oos_owner_authorization_v1",
        "authority": "owner_explicit_one_shot_reserved_diagnostic_only",
        "execute_once": True,
        "known_contamination_acknowledged": True,
        "money_authority": False,
        "reserved_window": {**WINDOW, "calendar_days": 273},
        "output_path": OUTPUT.as_posix(),
        "claim_path": CLAIM.as_posix(),
    }
    claim_exact = {
        "schema_id": "att1_sbr1_reserved_oos_one_shot_claim_v1",
        "state": "CLAIMED_BEFORE_MARKET_DECODE",
        "reserved_window": WINDOW,
        "output_path": OUTPUT.as_posix(),
        "claim_path": CLAIM.as_posix(),
    }
    receipt_exact = {
        "schema_id": "att1_sbr1_reserved_oos_one_shot_receipt_v1",
        "authority": (
            "research_only_reserved_diagnostic_no_live_no_broker_"
            "no_money_no_promotion"
        ),
        "reserved_window": WINDOW,
        "output_path": OUTPUT.as_posix(),
        "claim_path": CLAIM.as_posix(),
    }
    authorization_id = str(auth.get("owner_authorization_id") or "").strip()
    if (
        any(auth.get(key) != value for key, value in auth_exact.items())
        or not authorization_id
    ):
        raise FailureAuditViolation("authorization contract drift")
    if (
        any(claim.get(key) != value for key, value in claim_exact.items())
        or any(receipt.get(key) != value for key, value in receipt_exact.items())
    ):
        raise FailureAuditViolation("claim or receipt contract drift")


def verify_tracked_forensic_receipt(path: Path, fresh: Mapping[str, Any]) -> None:
    tracked = _object(path, "tracked forensic receipt")
    verify_forensic_receipt(tracked)
    if tracked != fresh:
        raise FailureAuditViolation("tracked forensic receipt drift")


def verify_forensic_receipt(receipt: Mapping[str, Any]) -> None:
    unsigned = dict(receipt)
    actual = str(unsigned.pop("forensic_receipt_sha256", ""))
    if actual != canonical_sha256(unsigned):
        raise FailureAuditViolation("forensic receipt self hash drift")
    identities = receipt.get("identities")
    economics = receipt.get("economics")
    if (
        set(receipt) != FORENSIC_RECEIPT_KEYS
        or receipt.get("schema_id") != "att1_sbr1_reserved_oos_failure_forensic_receipt_v1"
        or receipt.get("decision") != "AUDIT_CONFIRMED_FAIL_CLOSED_AFTER_CLAIM"
        or receipt.get("authority") != "research_only_failure_forensic_no_money_no_promotion"
        or receipt.get("root_cause") != ROOT_CAUSE
        or receipt.get("money_authority") is not False
        or receipt.get("promotion_authority") is not False
        or not isinstance(identities, Mapping)
        or set(identities) != IDENTITY_KEYS
        or not isinstance(economics, Mapping)
        or set(economics) != {"ATT1", "SBR1"}
    ):
        raise FailureAuditViolation("forensic receipt contract drift")

    hashes = [
        receipt.get("receipt_sha256"),
        receipt.get("claim_sha256"),
        *identities.values(),
    ]
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
        for value in hashes
    ):
        raise FailureAuditViolation("forensic receipt contract drift")

    expected_decisions = {
        "ATT1": "FAIL_CLOSED",
        "SBR1": "INCONCLUSIVE_LOW_N",
    }
    expected_block_keys = {
        "evaluation_sha256",
        "modes",
        "thresholds",
        "checks",
        "decision",
    }
    for sleeve, decision in expected_decisions.items():
        block = economics[sleeve]
        if (
            not isinstance(block, Mapping)
            or set(block) != expected_block_keys
            or block.get("decision") != decision
        ):
            raise FailureAuditViolation("forensic receipt contract drift")


def _canonical_json_line(row: Mapping[str, Any]) -> bytes:
    return json.dumps(
        row,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _validate_evaluation_signal(
    signal: object,
    row: Mapping[str, Any],
    sleeve: str,
    line_no: int,
) -> None:
    label = f"evaluation signal drift:{sleeve}:{line_no}"
    if signal is None:
        return
    if (
        not isinstance(signal, dict)
        or set(signal) != SIGNAL_KEYS
        or signal.get("symbol") != row["symbol"]
        or signal.get("side") != row["side_contract"]
        or not isinstance(signal.get("strategy"), str)
        or not signal["strategy"]
        or not isinstance(signal.get("reason"), str)
        or not signal["reason"]
        or type(signal.get("time_stop_bars")) is not int
        or signal["time_stop_bars"] <= 0
        or not isinstance(signal.get("tps"), list)
        or not signal["tps"]
        or not isinstance(signal.get("tp_fracs"), list)
        or len(signal["tps"]) != len(signal["tp_fracs"])
    ):
        raise FailureAuditViolation(label)

    numeric_strings = (
        [signal[name] for name in ("entry", "sl", "tp")]
        + signal["tps"]
        + signal["tp_fracs"]
    )
    if any(type(value) is not str or not value for value in numeric_strings):
        raise FailureAuditViolation(label)
    try:
        prices = [Decimal(signal[name]) for name in ("entry", "sl", "tp")]
        prices.extend(Decimal(value) for value in signal["tps"])
        fractions = [Decimal(value) for value in signal["tp_fracs"]]
    except (InvalidOperation, TypeError, ValueError):
        raise FailureAuditViolation(label) from None
    if any(value <= 0 or not value.is_finite() for value in prices):
        raise FailureAuditViolation(label)
    if any(value <= 0 or value > 1 or not value.is_finite() for value in fractions):
        raise FailureAuditViolation(label)


def _validate_evaluation_row(
    row: object,
    line: bytes,
    sleeve: str,
    line_no: int,
) -> tuple[str, int]:
    label = f"evaluation schema drift:{sleeve}:{line_no}"
    if not isinstance(row, dict) or set(row) != EVALUATION_KEYS:
        raise FailureAuditViolation(label)
    if _canonical_json_line(row) != line:
        raise FailureAuditViolation(label)
    if (
        row.get("sleeve_id") != sleeve
        or row.get("exception") is not None
        or type(row.get("eligible_regime")) is not bool
        or row.get("side_contract") != ("short" if sleeve == "ATT1" else "long")
        or row.get("symbol") not in MAJOR8
        or not isinstance(row.get("regime_value"), str)
        or row["regime_value"] not in REGIME_VALUES
    ):
        raise FailureAuditViolation(label)

    bar_ts = row.get("bar_ts")
    regime_bar_ts = row.get("regime_bar_ts")
    if (
        type(bar_ts) is not int
        or bar_ts < EVALUATION_START_TS_MS
        or bar_ts > EVALUATION_END_TS_MS
        or (bar_ts - EVALUATION_START_TS_MS) % EVALUATION_STEP_MS != 0
        or type(regime_bar_ts) is not int
        or regime_bar_ts <= 0
        or regime_bar_ts > bar_ts
    ):
        raise FailureAuditViolation(label)
    _validate_evaluation_signal(row["signal"], row, sleeve, line_no)
    return row["symbol"], bar_ts


def _evaluation_parity(output: Path, sleeve: str) -> str:
    prefix = sleeve.lower()
    research = output / f"{prefix}_evaluation_research.jsonl"
    live = output / f"{prefix}_evaluation_live.jsonl"
    if (
        _has_symlink_component(research)
        or _has_symlink_component(live)
        or not research.is_file()
        or not live.is_file()
    ):
        raise FailureAuditViolation(f"evaluation ledger missing:{sleeve}")
    raw = research.read_bytes()
    if raw != live.read_bytes() or not raw:
        raise FailureAuditViolation(f"evaluation byte parity drift:{sleeve}")

    seen: set[tuple[str, int]] = set()
    symbol_counts = {symbol: 0 for symbol in MAJOR8}
    for line_no, line in enumerate(raw.splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FailureAuditViolation(
                f"evaluation JSON drift:{sleeve}:{line_no}"
            ) from exc
        key = _validate_evaluation_row(row, line, sleeve, line_no)
        if key in seen:
            raise FailureAuditViolation(f"evaluation key drift:{sleeve}:{line_no}")
        seen.add(key)
        symbol_counts[key[0]] += 1

    expected_rows = len(MAJOR8) * EVALUATION_ROWS_PER_SYMBOL
    if len(seen) != expected_rows or any(
        count != EVALUATION_ROWS_PER_SYMBOL for count in symbol_counts.values()
    ):
        raise FailureAuditViolation(f"evaluation coverage drift:{sleeve}")
    return sha256_file(research)


def _decimal(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FailureAuditViolation(f"invalid decimal:{label}") from exc
    if not parsed.is_finite():
        raise FailureAuditViolation(f"invalid decimal:{label}")
    return parsed


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise FailureAuditViolation(f"invalid integer:{label}")
    return value


def _checks(
    metrics: Mapping[str, object],
    thresholds: Mapping[str, object],
) -> dict[str, bool]:
    try:
        halves = metrics["chronological_halves_r"]
        if not isinstance(halves, list) or len(halves) != 2:
            raise FailureAuditViolation("invalid metric contract:chronological_halves_r")

        n = _integer(metrics["n"], "metrics.n")
        minimum_n = _integer(thresholds["n_gte"], "thresholds.n_gte")
        mean_r = _decimal(metrics["mean_r"], "metrics.mean_r")
        minimum_mean_r = _decimal(thresholds["mean_r_gt"], "thresholds.mean_r_gt")
        profit_factor = metrics["profit_factor"]
        minimum_profit_factor = _decimal(
            thresholds["profit_factor_gte"],
            "thresholds.profit_factor_gte",
        )
        minimum_half_r = _decimal(
            thresholds["both_halves_r_gt"],
            "thresholds.both_halves_r_gt",
        )
        return {
            "n_gte": n >= minimum_n,
            "mean_r_gt": mean_r > minimum_mean_r,
            "profit_factor_gte": (
                profit_factor is not None
                and _decimal(profit_factor, "metrics.profit_factor")
                >= minimum_profit_factor
            ),
            "both_halves_r_gt": all(
                _decimal(value, "metrics.chronological_halves_r") > minimum_half_r
                for value in halves
            ),
            "max_sequential_drawdown_r_lte": _decimal(
                metrics["max_sequential_drawdown_r"],
                "metrics.max_sequential_drawdown_r",
            )
            <= _decimal(
                thresholds["max_sequential_drawdown_r_lte"],
                "thresholds.max_sequential_drawdown_r_lte",
            ),
            "positive_month_fraction_gte": _decimal(
                metrics["positive_month_fraction"],
                "metrics.positive_month_fraction",
            )
            >= _decimal(
                thresholds["positive_month_fraction_gte"],
                "thresholds.positive_month_fraction_gte",
            ),
            "positive_symbol_concentration_lte": _decimal(
                metrics["positive_symbol_concentration"],
                "metrics.positive_symbol_concentration",
            )
            <= _decimal(
                thresholds["positive_symbol_concentration_lte"],
                "thresholds.positive_symbol_concentration_lte",
            ),
            "minimum_leave_one_symbol_out_r_gt": _decimal(
                metrics["minimum_leave_one_symbol_out_r"],
                "metrics.minimum_leave_one_symbol_out_r",
            )
            > _decimal(
                thresholds["minimum_leave_one_symbol_out_r_gt"],
                "thresholds.minimum_leave_one_symbol_out_r_gt",
            ),
        }
    except KeyError as exc:
        raise FailureAuditViolation(f"invalid metric contract:{exc.args[0]}") from exc


def _decision(
    base: Mapping[str, object],
    stress: Mapping[str, object],
    thresholds: Mapping[str, object],
    negative_stress_n: int,
) -> str:
    base_passes = all(_checks(base, thresholds).values())
    stress_passes = all(_checks(stress, thresholds).values())
    if base_passes and stress_passes:
        return "PASS_ZERO_RISK_INTEGRATION_ONLY"
    base_n = _integer(base.get("n"), "base.n")
    stress_n = _integer(stress.get("n"), "stress.n")
    gate_n = _integer(thresholds.get("n_gte"), "thresholds.n_gte")
    negative_gate_n = _integer(negative_stress_n, "negative_stress_n")
    if (base_n >= gate_n and stress_n >= gate_n) or (
        stress_n >= negative_gate_n
        and _decimal(stress.get("sum_r"), "stress.sum_r") < 0
    ):
        return "FAIL_CLOSED"
    return "INCONCLUSIVE_LOW_N"


def _build_identities(root: Path) -> dict[str, str]:
    return {
        "config_sha256": sha256_file(root / CONFIG),
        "input_manifest_sha256": sha256_file(
            root / "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json"
        ),
        "runner_sha256": sha256_file(
            root / "scripts/run_att1_sbr1_reserved_oos_v1.py"
        ),
        "audit_sha256": sha256_file(
            root / "scripts/audit_att1_sbr1_reserved_oos_v1.py"
        ),
        "authorization_sha256": sha256_file(root / AUTH),
    }


def _validate_run_context(
    root: Path,
    auth: Mapping[str, Any],
    claim: Mapping[str, Any],
    receipt: Mapping[str, Any],
    identities: Mapping[str, str],
) -> None:
    auth_identity_keys = set(identities) - {"authorization_sha256"}
    if any(auth.get(key) != identities[key] for key in auth_identity_keys):
        raise FailureAuditViolation("identity drift")
    if any(
        claim.get(key) != value or receipt.get(key) != value
        for key, value in identities.items()
    ):
        raise FailureAuditViolation("identity drift")
    _validate_auth_claim_receipt(auth, claim, receipt)

    claim_path = root / CLAIM
    if receipt.get("claim_sha256") != sha256_file(claim_path):
        raise FailureAuditViolation("claim or window drift")
    zero_authority = {
        "private_api_calls": 0,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "money_authority": False,
        "promotion_authority": False,
    }
    if any(
        claim.get(key) != value or receipt.get(key) != value
        for key, value in zero_authority.items()
    ):
        raise FailureAuditViolation("authority drift")

    claim_time = _parse_time(claim.get("claim_created_at_utc"), "claim")
    decode_start = _parse_time(
        receipt.get("market_decode_started_at_utc"),
        "decode start",
    )
    decode_finish = _parse_time(
        receipt.get("market_decode_finished_at_utc"),
        "decode finish",
    )
    terminal_time = _parse_time(receipt.get("terminal_at_utc"), "terminal")
    if not claim_time <= decode_start <= decode_finish <= terminal_time:
        raise FailureAuditViolation("failure timing drift")


def _load_threshold_receipt(
    root: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    expected_path = Path(
        "research_lab/results/att1_sbr1_presealed_economics_"
        "diagnostic_20260823/receipt.json"
    )
    source = config.get("threshold_source")
    pin = _validated_source_pin(
        root,
        config,
        "presealed_thresholds",
        expected_path,
        "threshold pin drift",
    )
    if not isinstance(source, Mapping):
        raise FailureAuditViolation("threshold pin drift")
    if (
        source.get("path") != expected_path.as_posix()
        or source.get("sha256") != pin.get("sha256")
    ):
        raise FailureAuditViolation("threshold pin drift")
    return _object(root / expected_path, "threshold receipt")


def _sleeve_thresholds(
    threshold_receipt: Mapping[str, Any],
    sleeve: str,
) -> Mapping[str, Any]:
    try:
        thresholds = threshold_receipt["sleeves"][sleeve][
            "zero_risk_shadow_gate"
        ]["thresholds"]
    except (KeyError, TypeError) as exc:
        raise FailureAuditViolation(f"threshold contract drift:{sleeve}") from exc
    if not isinstance(thresholds, Mapping) or set(thresholds) != THRESHOLD_KEYS:
        raise FailureAuditViolation(f"threshold contract drift:{sleeve}")
    return thresholds


def _audit_mode(output: Path, sleeve: str, mode: str) -> dict[str, Any]:
    from research_lab.adapter_parity import LedgerError, compare_ledgers, read_jsonl
    from research_lab.summarize_att1_sbr1_presealed_economics import (
        DiagnosticViolation,
        chronological_symbol_occupancy,
        metrics,
    )

    prefix = f"{sleeve.lower()}_{mode}"
    research_path = output / f"{prefix}_research.jsonl"
    live_path = output / f"{prefix}_live.jsonl"
    try:
        research = read_jsonl(research_path)
        live = read_jsonl(live_path)
        comparison = compare_ledgers(research, live)
    except (LedgerError, KeyError, TypeError, ValueError) as exc:
        raise FailureAuditViolation(
            f"normalized evidence drift:{sleeve}:{mode}"
        ) from exc
    if comparison.get("decision") != "PASS":
        raise FailureAuditViolation(f"normalized parity drift:{sleeve}:{mode}")

    report = _object(output / f"{prefix}_parity_report.json", "parity report")
    expected_report = {
        **comparison,
        "research_ledger_sha256": sha256_file(research_path),
        "live_ledger_sha256": sha256_file(live_path),
    }
    if set(report) != PARITY_REPORT_KEYS or report != expected_report:
        raise FailureAuditViolation(f"parity report drift:{sleeve}:{mode}")

    try:
        accepted = chronological_symbol_occupancy(tuple(live.values()), sleeve)
        accepted_metrics = metrics(accepted.rows)
    except (DiagnosticViolation, KeyError, TypeError, ValueError) as exc:
        raise FailureAuditViolation(
            f"occupancy or metrics drift:{sleeve}:{mode}"
        ) from exc
    return {
        "raw_signals": len(live),
        "accepted_signals": len(accepted.rows),
        "same_symbol_occupancy_drops": accepted.overlap_drops,
        "metrics": accepted_metrics,
    }


def _build_economics(
    output: Path,
    config: Mapping[str, Any],
    threshold_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    decision_contract = config.get("decision_contract")
    if not isinstance(decision_contract, Mapping):
        raise FailureAuditViolation("decision contract drift")
    negative_gate_n = _integer(
        decision_contract.get("negative_stress_sum_r_is_fail_when_n_gte"),
        "decision_contract.negative_stress_sum_r_is_fail_when_n_gte",
    )

    economics: dict[str, Any] = {}
    for sleeve in ("ATT1", "SBR1"):
        modes = {
            mode: _audit_mode(output, sleeve, mode)
            for mode in ("base", "stress")
        }
        thresholds = _sleeve_thresholds(threshold_receipt, sleeve)
        checks = {
            mode: _checks(modes[mode]["metrics"], thresholds)
            for mode in ("base", "stress")
        }
        decision = _decision(
            modes["base"]["metrics"],
            modes["stress"]["metrics"],
            thresholds,
            negative_gate_n,
        )
        economics[sleeve] = {
            "evaluation_sha256": _evaluation_parity(output, sleeve),
            "modes": modes,
            "thresholds": thresholds,
            "checks": checks,
            "decision": decision,
        }
    expected_decisions = {
        "ATT1": "FAIL_CLOSED",
        "SBR1": "INCONCLUSIVE_LOW_N",
    }
    if any(
        economics[sleeve]["decision"] != decision
        for sleeve, decision in expected_decisions.items()
    ):
        raise FailureAuditViolation("informational economics drift")
    return economics


def audit_failure(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    config = _object(root / CONFIG, "config")
    auth = _object(root / AUTH, "authorization")
    claim_path = root / CLAIM
    receipt_path = root / RECEIPT
    output = root / OUTPUT
    claim = _object(claim_path, "claim")
    receipt = _object(receipt_path, "failure receipt")
    verify_receipt(receipt)

    identities = _build_identities(root)
    _validate_run_context(root, auth, claim, receipt, identities)
    _validate_accounting(
        root,
        config,
        receipt.get("decode_accounting"),
        receipt.get("market_decode_started_at_utc"),
        receipt.get("market_decode_finished_at_utc"),
    )
    _validate_output_inventories(receipt, output)
    threshold_receipt = _load_threshold_receipt(root, config)
    economics = _build_economics(output, config, threshold_receipt)

    result: dict[str, Any] = {
        "schema_id": "att1_sbr1_reserved_oos_failure_forensic_receipt_v1",
        "authority": "research_only_failure_forensic_no_money_no_promotion",
        "decision": "AUDIT_CONFIRMED_FAIL_CLOSED_AFTER_CLAIM",
        "root_cause": ROOT_CAUSE,
        "receipt_sha256": sha256_file(receipt_path),
        "claim_sha256": sha256_file(claim_path),
        "identities": identities,
        "economics": economics,
        "money_authority": False,
        "promotion_authority": False,
    }
    result["forensic_receipt_sha256"] = canonical_sha256(result)
    return result


if __name__ == "__main__":
    fresh = audit_failure()
    verify_forensic_receipt(fresh)
    verify_tracked_forensic_receipt(ROOT / "reports/receipts/ATT1_SBR1_RESERVED_OOS_FAILURE_FORENSIC_2026_08_29.json", fresh)
    print(json.dumps(fresh, sort_keys=True, indent=2))
