#!/usr/bin/env python3
"""Summarise ATT1/SBR1 pre-sealed parity outcomes without granting money authority.

The parity runner intentionally emits every eligible signal so the research and
live-shaped boundaries can be compared.  This diagnostic applies chronological
same-symbol occupancy using the replayed accepted-fill and exit timestamps.

The result may authorise a prospective zero-risk shadow only.  It is not an OOS,
multiple-testing, broker-fill, profitability, promotion, risk, or money gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path(
    "research_lab/results/att1_sbr1_actual_adapter_parity_presealed_v1_20260823"
)
DEFAULT_OUTPUT = Path(
    "research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json"
)


class DiagnosticViolation(RuntimeError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise DiagnosticViolation(f"invalid_decimal:{field}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DiagnosticViolation(f"invalid_decimal:{field}") from exc
    if not result.is_finite():
        raise DiagnosticViolation(f"invalid_decimal:{field}")
    return result


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise DiagnosticViolation(f"invalid_integer:{field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DiagnosticViolation(f"invalid_integer:{field}") from exc
    if not result.is_finite() or result != result.to_integral_value():
        raise DiagnosticViolation(f"invalid_integer:{field}")
    return int(result)


@dataclass(frozen=True)
class AcceptedRows:
    rows: tuple[Mapping[str, object], ...]
    overlap_drops: int


def validate_row(row: Mapping[str, object], sleeve: str) -> None:
    if row.get("schema_id") != "research_live_adapter_parity_v2":
        raise DiagnosticViolation("wrong_row_schema")
    if str(row.get("sleeve_id") or "").upper() != sleeve:
        raise DiagnosticViolation("wrong_row_sleeve")
    if row.get("release_or_promotion_authority") is not False:
        raise DiagnosticViolation("unexpected_release_authority")
    if row.get("exception") is not None:
        raise DiagnosticViolation("row_exception")
    bar_ts = _strict_int(row.get("bar_ts"), "bar_ts")
    time_stop = row.get("time_stop")
    if not isinstance(time_stop, Mapping):
        raise DiagnosticViolation("missing_time_stop")
    deadline = _strict_int(time_stop.get("deadline_ms"), "deadline_ms")
    if deadline <= bar_ts:
        raise DiagnosticViolation("noncausal_deadline")
    if not str(row.get("symbol") or "").endswith("USDT"):
        raise DiagnosticViolation("invalid_symbol")
    if not str(row.get("signal_id") or ""):
        raise DiagnosticViolation("missing_signal_id")
    fill_ts = _strict_int(row.get("fill_ts_ms"), "fill_ts_ms")
    exit_ts = _strict_int(row.get("exit_ts_ms"), "exit_ts_ms")
    if fill_ts < bar_ts or exit_ts < fill_ts or exit_ts > deadline:
        raise DiagnosticViolation("invalid_trade_lifecycle")
    _decimal(row.get("net_r"), "net_r")


def chronological_symbol_occupancy(
    rows: Iterable[Mapping[str, object]], sleeve: str
) -> AcceptedRows:
    ordered = sorted(
        rows,
        key=lambda row: (
            _strict_int(row.get("bar_ts"), "bar_ts"),
            str(row.get("symbol") or ""),
            str(row.get("signal_id") or ""),
        ),
    )
    busy_until: dict[str, int] = {}
    accepted: list[Mapping[str, object]] = []
    seen: set[str] = set()
    drops = 0
    for row in ordered:
        validate_row(row, sleeve)
        signal_id = str(row["signal_id"])
        if signal_id in seen:
            raise DiagnosticViolation("duplicate_signal_id")
        seen.add(signal_id)
        symbol = str(row["symbol"])
        fill_ts = _strict_int(row["fill_ts_ms"], "fill_ts_ms")
        exit_ts = _strict_int(row["exit_ts_ms"], "exit_ts_ms")
        if fill_ts < busy_until.get(symbol, 0):
            drops += 1
            continue
        accepted.append(row)
        busy_until[symbol] = exit_ts
    return AcceptedRows(tuple(accepted), drops)


def metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not rows:
        raise DiagnosticViolation("empty_accepted_rows")
    ordered = sorted(rows, key=lambda row: (int(row["bar_ts"]), str(row["symbol"])))
    values = [_decimal(row["net_r"], "net_r") for row in ordered]
    positive = sum((value for value in values if value > 0), Decimal("0"))
    negative = -sum((value for value in values if value < 0), Decimal("0"))
    cumulative = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    month_counts: dict[str, int] = defaultdict(int)
    for row, value in zip(ordered, values):
        symbol = str(row["symbol"])
        month = datetime.fromtimestamp(
            int(row["bar_ts"]) / 1000, timezone.utc
        ).strftime("%Y-%m")
        by_symbol[symbol] += value
        by_month[month] += value
        month_counts[month] += 1

    positive_symbols = [value for value in by_symbol.values() if value > 0]
    positive_symbol_total = sum(positive_symbols, Decimal("0"))
    concentration = (
        max(positive_symbols) / positive_symbol_total
        if positive_symbol_total > 0
        else Decimal("1")
    )
    leave_one_out = {
        symbol: sum(values, Decimal("0")) - value
        for symbol, value in sorted(by_symbol.items())
    }
    half = len(values) // 2
    first_half = sum(values[:half], Decimal("0"))
    second_half = sum(values[half:], Decimal("0"))
    return {
        "n": len(values),
        "sum_r": _decimal_text(sum(values, Decimal("0"))),
        "mean_r": _decimal_text(sum(values, Decimal("0")) / Decimal(len(values))),
        "win_rate": _decimal_text(
            Decimal(sum(value > 0 for value in values)) / Decimal(len(values))
        ),
        "profit_factor": _decimal_text(positive / negative) if negative > 0 else None,
        "max_sequential_drawdown_r": _decimal_text(max_drawdown),
        "chronological_halves_r": [
            _decimal_text(first_half),
            _decimal_text(second_half),
        ],
        "positive_months": sum(value > 0 for value in by_month.values()),
        "months": len(by_month),
        "positive_month_fraction": _decimal_text(
            Decimal(sum(value > 0 for value in by_month.values()))
            / Decimal(len(by_month))
        ),
        "positive_symbol_concentration": _decimal_text(concentration),
        "by_symbol_r": {
            symbol: _decimal_text(value) for symbol, value in sorted(by_symbol.items())
        },
        "leave_one_symbol_out_r": {
            symbol: _decimal_text(value) for symbol, value in leave_one_out.items()
        },
        "minimum_leave_one_symbol_out_r": _decimal_text(min(leave_one_out.values())),
        "by_month": {
            month: {"n": month_counts[month], "sum_r": _decimal_text(by_month[month])}
            for month in sorted(by_month)
        },
    }


def zero_risk_shadow_gate(stress: Mapping[str, object]) -> dict[str, object]:
    thresholds = {
        "n_gte": 40,
        "mean_r_gt": "0.10",
        "profit_factor_gte": "1.40",
        "both_halves_r_gt": "0",
        "max_sequential_drawdown_r_lte": "10",
        "positive_month_fraction_gte": "0.55",
        "positive_symbol_concentration_lte": "0.35",
        "minimum_leave_one_symbol_out_r_gt": "0",
    }
    checks = {
        "n": int(stress["n"]) >= thresholds["n_gte"],
        "mean_r": _decimal(stress["mean_r"], "mean_r") > Decimal("0.10"),
        "profit_factor": stress["profit_factor"] is not None
        and _decimal(stress["profit_factor"], "profit_factor") >= Decimal("1.40"),
        "both_halves": all(
            _decimal(value, "half_r") > 0 for value in stress["chronological_halves_r"]
        ),
        "drawdown": _decimal(
            stress["max_sequential_drawdown_r"], "max_drawdown"
        )
        <= Decimal("10"),
        "positive_month_fraction": _decimal(
            stress["positive_month_fraction"], "positive_month_fraction"
        )
        >= Decimal("0.55"),
        "concentration": _decimal(
            stress["positive_symbol_concentration"], "concentration"
        )
        <= Decimal("0.35"),
        "leave_one_symbol_out": _decimal(
            stress["minimum_leave_one_symbol_out_r"], "minimum_loso"
        )
        > 0,
    }
    return {
        "decision": "PASS_ZERO_RISK_SHADOW_ONLY" if all(checks.values()) else "FAIL_CLOSED",
        "checks": checks,
        "thresholds": thresholds,
        "authority": "prospective_zero_risk_shadow_only",
        "money_authority": False,
    }


def _read_jsonl(path: Path) -> list[Mapping[str, object]]:
    result: list[Mapping[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, Mapping):
            raise DiagnosticViolation(f"non_object_row:{path}:{line_number}")
        result.append(value)
    return result


def run(root: Path, input_dir: Path, output: Path) -> dict[str, object]:
    source = input_dir if input_dir.is_absolute() else root / input_dir
    target = output if output.is_absolute() else root / output
    parity_path = source / "receipt.json"
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    if (
        parity.get("decision") != "COMPONENT_PARITY_PASS"
        or parity.get("live_caller_parity") != "BLOCKED"
        or parity.get("money_authority") is not False
    ):
        raise DiagnosticViolation("parity_not_research_only_pass")
    if int(parity.get("sealed_holdout_rows_decoded", -1)) != 0:
        raise DiagnosticViolation("sealed_rows_were_decoded")

    sleeves: dict[str, object] = {}
    input_hashes: dict[str, str] = {
        "receipt.json": _sha_bytes(parity_path.read_bytes())
    }
    for sleeve in ("ATT1", "SBR1"):
        modes: dict[str, object] = {}
        for mode in ("base", "stress"):
            filename = f"{sleeve.lower()}_{mode}_live.jsonl"
            path = source / filename
            input_hashes[filename] = _sha_bytes(path.read_bytes())
            raw_rows = _read_jsonl(path)
            accepted = chronological_symbol_occupancy(raw_rows, sleeve)
            modes[mode] = {
                "raw_signals": len(raw_rows),
                "accepted_signals": len(accepted.rows),
                "same_symbol_occupancy_drops": accepted.overlap_drops,
                "metrics": metrics(accepted.rows),
            }
        sleeves[sleeve] = {
            "modes": modes,
            "zero_risk_shadow_gate": zero_risk_shadow_gate(modes["stress"]["metrics"]),
        }

    receipt: dict[str, object] = {
        "schema_id": "att1_sbr1_presealed_economics_diagnostic_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decision": {
            sleeve: sleeves[sleeve]["zero_risk_shadow_gate"]["decision"]
            for sleeve in ("ATT1", "SBR1")
        },
        "authority": "research_only_or_prospective_zero_risk_shadow",
        "money_authority": False,
        "release_or_promotion_authority": False,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "sealed_holdout_rows_decoded": 0,
        "parity_receipt_sha256": input_hashes["receipt.json"],
        "input_sha256": input_hashes,
        "occupancy_contract": {
            "rule": "one accepted signal per sleeve and symbol from accepted fill until replayed exit timestamp",
            "remaining_limit": "Global slots, cross-sleeve correlation and risk budget are not scored here; the prospective shadow must enforce them.",
        },
        "sleeves": sleeves,
        "what_pass_means": "Only that a fixed sleeve cleared conservative descriptive thresholds for prospective zero-risk shadow collection.",
        "what_pass_does_not_mean": "No OOS, multiple-testing, profitability, broker-fill, live promotion, risk, or money authority is granted.",
        "binding_next_gate": "default-off production caller parity plus prospective zero-order shadow with durable simulated decision_fill_exit receipts",
    }
    receipt["receipt_sha256"] = _sha_bytes(_canonical_bytes(receipt))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        receipt = run(args.root, args.input, args.output)
    except Exception as exc:
        print(json.dumps({"decision": "FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"}))
        return 2
    print(json.dumps({
        "decision": receipt["decision"],
        "money_authority": receipt["money_authority"],
        "receipt_sha256": receipt["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
