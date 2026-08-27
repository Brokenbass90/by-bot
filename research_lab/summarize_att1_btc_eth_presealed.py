#!/usr/bin/env python3
"""Describe frozen pre-sealed ATT1 outcomes for BTC, ETH, and major8 peers.

This is a post-hoc descriptive cohort split of an already frozen live-native
adapter ledger.  It does not search parameters, decode reserved rows, call a
broker, or grant shadow/live/money authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.summarize_att1_sbr1_presealed_economics import (
    DiagnosticViolation,
    _decimal,
    _decimal_text,
    chronological_symbol_occupancy,
    metrics,
)


DEFAULT_OUTPUT = ROOT / "research_lab/results/att1_btc_eth_presealed_diagnostic_v1_20260827/receipt.json"
DEFAULT_CONFIG = ROOT / "configs/research/att1_btc_eth_presealed_diagnostic_v1.json"
DEFAULT_UNIVERSE = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "DOTUSDT",
    "SUIUSDT",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _load_contract(path: Path) -> dict[str, object]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = contract.pop("config_fingerprint_sha256", None)
    if fingerprint != _canonical_sha256(contract):
        raise DiagnosticViolation("diagnostic contract fingerprint mismatch")
    contract["config_fingerprint_sha256"] = fingerprint
    if (
        contract.get("schema_id") != "att1_btc_eth_presealed_diagnostic_contract_v1"
        or contract.get("authority")
        != "research_only_exact_frozen_input_no_live_no_broker_no_money_no_promotion"
    ):
        raise DiagnosticViolation("diagnostic contract authority changed")
    return contract


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_jsonl(path: Path) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, Mapping):
            raise DiagnosticViolation(f"non_object_row:{path}:{line_number}")
        rows.append(value)
    return rows


def _empty_metrics() -> dict[str, object]:
    return {
        "n": 0,
        "sum_r": "0",
        "mean_r": None,
        "win_rate": None,
        "profit_factor": None,
        "max_sequential_drawdown_r": "0",
        "chronological_halves_r": ["0", "0"],
        "positive_months": 0,
        "months": 0,
        "positive_month_fraction": None,
        "positive_symbol_concentration": None,
        "by_symbol_r": {},
        "leave_one_symbol_out_r": {},
        "minimum_leave_one_symbol_out_r": None,
        "by_month": {},
    }


def build_cohort_diagnostics(
    rows: Sequence[Mapping[str, object]],
    *,
    universe: Sequence[str],
) -> dict[str, object]:
    accepted = chronological_symbol_occupancy(rows, "ATT1")
    cohort_symbols = {
        "btc_only": ("BTCUSDT",),
        "eth_only": ("ETHUSDT",),
        "btc_eth": ("BTCUSDT", "ETHUSDT"),
        "major8_ex_btc_eth": tuple(
            symbol for symbol in universe if symbol not in {"BTCUSDT", "ETHUSDT"}
        ),
        "major8_all": tuple(universe),
    }
    result: dict[str, object] = {}
    for name, symbols in cohort_symbols.items():
        symbol_set = set(symbols)
        raw_subset = [row for row in rows if str(row.get("symbol")) in symbol_set]
        accepted_subset = [
            row for row in accepted.rows if str(row.get("symbol")) in symbol_set
        ]
        report = metrics(accepted_subset) if accepted_subset else _empty_metrics()
        by_side_n: dict[str, int] = defaultdict(int)
        by_side_r: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in accepted_subset:
            side = str(row.get("side") or "unknown")
            by_side_n[side] += 1
            by_side_r[side] += _decimal(row.get("net_r"), "net_r")
        report["by_side_n"] = dict(sorted(by_side_n.items()))
        report["by_side_r"] = {
            side: _decimal_text(value) for side, value in sorted(by_side_r.items())
        }
        report["side_trade_fraction"] = {
            side: _decimal_text(Decimal(count) / Decimal(len(accepted_subset)))
            for side, count in sorted(by_side_n.items())
        }
        report["max_side_trade_fraction"] = (
            max(report["side_trade_fraction"].values())
            if report["side_trade_fraction"]
            else None
        )
        result[name] = {
            "symbols": list(symbols),
            "raw_signals": len(raw_subset),
            "accepted_signals": len(accepted_subset),
            "same_symbol_occupancy_drops": len(raw_subset) - len(accepted_subset),
            "metrics": report,
        }
    return result


def _descriptive_label(base: Mapping[str, object], stress: Mapping[str, object]) -> str:
    if int(base.get("n") or 0) == 0 or int(stress.get("n") or 0) == 0:
        return "NO_TRADES"
    base_sum = _decimal(base.get("sum_r"), "base_sum_r")
    stress_sum = _decimal(stress.get("sum_r"), "stress_sum_r")
    if base_sum > 0 and stress_sum > 0:
        return "DESCRIPTIVE_POSITIVE_BOTH_COSTS"
    if base_sum < 0 and stress_sum < 0:
        return "DESCRIPTIVE_NEGATIVE_BOTH_COSTS"
    return "DESCRIPTIVE_MIXED_COST_SENSITIVITY"


def run(
    input_dir: Path,
    output: Path,
    *,
    universe: Sequence[str] | None = None,
    contract_path: Path = DEFAULT_CONFIG,
) -> dict[str, object]:
    contract = _load_contract(contract_path)
    frozen_universe = tuple(str(value) for value in contract.get("universe", []))
    if frozen_universe != DEFAULT_UNIVERSE:
        raise DiagnosticViolation("frozen universe changed")
    if universe is not None and tuple(universe) != frozen_universe:
        raise DiagnosticViolation("caller universe differs from frozen contract")
    universe = frozen_universe
    expected = contract.get("expected_source")
    if not isinstance(expected, Mapping):
        raise DiagnosticViolation("expected source identity missing")
    source = input_dir.resolve()
    parity_path = source / "receipt.json"
    parity_file_sha = _sha256_file(parity_path)
    if parity_file_sha != expected.get("receipt_file_sha256"):
        raise DiagnosticViolation("frozen source receipt file hash mismatch")
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    if (
        parity.get("decision") != "COMPONENT_PARITY_PASS"
        or parity.get("live_caller_parity") != "BLOCKED"
        or parity.get("money_authority") is not False
        or int(parity.get("sealed_holdout_rows_decoded", -1)) != 0
    ):
        raise DiagnosticViolation("source parity receipt is not the frozen research-only input")
    for key in ("receipt_sha256", "manifest_path", "manifest_sha256", "data_bundle_sha256", "source_bundle_sha256"):
        if parity.get(key) != expected.get(key):
            raise DiagnosticViolation(f"frozen source identity mismatch:{key}")
    parity_for_hash = dict(parity)
    internal_hash = parity_for_hash.pop("receipt_sha256", None)
    if internal_hash != _canonical_sha256(parity_for_hash):
        raise DiagnosticViolation("source receipt internal hash mismatch")
    if parity.get("window") != {
        "start_utc": "2024-03-01T00:00:00Z",
        "end_utc_exclusive": "2025-10-01T00:00:00Z",
    }:
        raise DiagnosticViolation("unexpected presealed window")
    if parity.get("sealed_holdout_guard") != {
        "start_utc": "2025-10-01T00:00:00Z",
        "end_utc_exclusive": "2026-07-01T00:00:00Z",
        "must_not_read": True,
    }:
        raise DiagnosticViolation("sealed guard changed")

    sleeve = parity.get("sleeves", {}).get("ATT1", {})
    reports = sleeve.get("reports", {}) if isinstance(sleeve, Mapping) else {}
    modes: dict[str, object] = {}
    input_hashes = {"receipt.json": parity_file_sha}
    for mode in ("base", "stress"):
        path = source / f"att1_{mode}_live.jsonl"
        actual_sha = _sha256_file(path)
        expected_report = reports.get(mode, {}) if isinstance(reports, Mapping) else {}
        expected_sha = (
            str(expected_report.get("live_ledger_sha256") or "")
            if isinstance(expected_report, Mapping)
            else ""
        )
        frozen_ledger_sha = expected.get(f"att1_{mode}_live_sha256")
        if actual_sha != expected_sha or actual_sha != frozen_ledger_sha:
            raise DiagnosticViolation(f"frozen ledger hash mismatch:{mode}")
        rows = _read_jsonl(path)
        unknown = sorted({str(row.get("symbol") or "") for row in rows} - set(universe))
        if unknown:
            raise DiagnosticViolation(f"unexpected symbols:{','.join(unknown)}")
        input_hashes[path.name] = actual_sha
        modes[mode] = {"cohorts": build_cohort_diagnostics(rows, universe=universe)}

    labels = {
        cohort: _descriptive_label(
            modes["base"]["cohorts"][cohort]["metrics"],
            modes["stress"]["cohorts"][cohort]["metrics"],
        )
        for cohort in modes["base"]["cohorts"]
    }
    receipt: dict[str, object] = {
        "schema_id": "att1_btc_eth_presealed_diagnostic_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decision": "DESCRIPTIVE_ONLY_NO_PROMOTION",
        "authority": "research_only_post_hoc_cohort_attribution",
        "money_authority": False,
        "release_or_promotion_authority": False,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "sealed_holdout_rows_decoded": 0,
        "parameter_search_or_retuning": False,
        "post_hoc_cohort_split": True,
        "window": dict(parity["window"]),
        "sealed_holdout_guard": dict(parity["sealed_holdout_guard"]),
        "universe": list(universe),
        "frozen_contract": {
            "path": str(contract_path.resolve()),
            "sha256": _sha256_file(contract_path),
            "fingerprint_sha256": contract["config_fingerprint_sha256"],
        },
        "implementation": {
            "path": "research_lab/summarize_att1_btc_eth_presealed.py",
            "sha256": _sha256_file(Path(__file__).resolve()),
        },
        "source_directory": str(source),
        "input_sha256": input_hashes,
        "modes": modes,
        "descriptive_labels": labels,
        "interpretation_rule": (
            "Symbol cohorts describe the already-frozen major8 ledger only. "
            "They may falsify portability but cannot select new parameters or authorize money."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    _atomic_json(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="directory containing the frozen, hash-receipted parity ledgers",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        receipt = run(args.input, args.output)
    except Exception as exc:
        print(json.dumps({"decision": "FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"}))
        return 2
    print(
        json.dumps(
            {
                "decision": receipt["decision"],
                "descriptive_labels": receipt["descriptive_labels"],
                "receipt_sha256": receipt["receipt_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
