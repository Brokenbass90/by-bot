#!/usr/bin/env python3
"""Independent invariant and data-coverage check for the Alpaca diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv  # noqa: E402


DEFAULT_RECEIPT = ROOT / "reports" / "research" / "alpaca_honest_diagnostic_v1_20260810" / "receipt.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "alpaca_honest_diagnostic_v1_20260810" / "validation_receipt.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _drawdown(initial: float, values: list[float]) -> float:
    peak = initial
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return worst * 100.0


def _dates_for_manifest_row(row: dict[str, Any]) -> set[str]:
    path = ROOT / str(row["path"])
    source = str(row["source"])
    if source == "yfinance_auto_adjust_true_cache":
        try:
            frame = pd.read_csv(path, usecols=["Date"])
            values = pd.to_datetime(frame["Date"], errors="coerce")
        except ValueError:
            frame = pd.read_csv(path, header=[0, 1], index_col=0)
            values = pd.to_datetime(frame.index, errors="coerce")
        return {value.date().isoformat() for value in values if not pd.isna(value)}
    if source == "cached_intraday_aggregate":
        return {
            datetime.fromtimestamp(int(candle.ts), timezone.utc).date().isoformat()
            for candle in load_m5_csv(str(path))
        }
    raise ValueError(f"unsupported source {source}")


def _validate_result(row: dict[str, Any], embargo: date) -> list[str]:
    issues: list[str] = []
    summary = row["summary"]
    daily = row["daily_equity"]
    sessions = [str(item["session"]) for item in daily]
    equities = [float(item["equity"]) for item in daily]
    initial = float(summary["initial_capital"])
    if sessions != sorted(set(sessions)):
        issues.append("daily_sessions_not_unique_ordered")
    if any(date.fromisoformat(session) >= embargo for session in sessions):
        issues.append("embargoed_daily_outcome_present")
    if not daily:
        issues.append("daily_equity_empty")
        return issues
    expected_final = equities[-1]
    if not math.isclose(float(summary["final_equity"]), expected_final, rel_tol=0, abs_tol=1e-8):
        issues.append("final_equity_mismatch")
    expected_return = (expected_final / initial - 1.0) * 100.0
    if not math.isclose(float(summary["return_pct"]), expected_return, rel_tol=0, abs_tol=1e-8):
        issues.append("return_mismatch")
    if not math.isclose(float(summary["daily_max_drawdown_pct"]), _drawdown(initial, equities), rel_tol=0, abs_tol=1e-8):
        issues.append("drawdown_mismatch")
    if any(float(item["cash"]) < -1e-8 for item in daily):
        issues.append("negative_cash")
    if any(not 0.0 <= float(item["gross_exposure"]) <= 1.000001 for item in daily):
        issues.append("gross_exposure_out_of_range")
    for decision in row["decisions"]:
        if date.fromisoformat(str(decision["signal_session"])) >= date.fromisoformat(str(decision["entry_session"])):
            issues.append("noncausal_signal_entry_order")
            break
    wins = 0.0
    losses = 0.0
    for trade in row["trades"]:
        if date.fromisoformat(str(trade["exit_session"])) >= embargo:
            issues.append("embargoed_trade_present")
        expected_pnl = float(trade["qty"]) * (float(trade["exit_fill"]) - float(trade["entry_fill"]))
        if not math.isclose(float(trade["pnl"]), expected_pnl, rel_tol=0, abs_tol=1e-8):
            issues.append("trade_pnl_mismatch")
        if expected_pnl > 0:
            wins += expected_pnl
        elif expected_pnl < 0:
            losses -= expected_pnl
    expected_pf = wins / losses if losses > 0 else None
    actual_pf = summary["profit_factor_realized"]
    if expected_pf is None:
        if actual_pf is not None:
            issues.append("profit_factor_mismatch")
    elif actual_pf is None or not math.isclose(float(actual_pf), expected_pf, rel_tol=0, abs_tol=1e-8):
        issues.append("profit_factor_mismatch")
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT.relative_to(ROOT)))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT.relative_to(ROOT)))
    args = parser.parse_args()
    receipt_path = ROOT / args.receipt
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    config_path = ROOT / str(receipt["config_path"])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    embargo = date.fromisoformat(str(receipt["outcome_embargo_start_session"]))

    result_checks = []
    all_issues: list[str] = []
    for row in receipt["results"]:
        issues = _validate_result(row, embargo)
        all_issues.extend(issues)
        result_checks.append(
            {
                "window": row["window"],
                "arm": row["arm"],
                "cost_bps_per_side": row["cost_bps_per_side"],
                "ok": not issues,
                "issues": issues,
            }
        )

    pin_checks = []
    for name, pin in config["source_pins"].items():
        path = ROOT / str(pin["path"])
        actual = _sha256(path) if path.is_file() else None
        pin_checks.append({"name": name, "ok": actual == pin["sha256"], "actual_sha256": actual})
        if actual != pin["sha256"]:
            all_issues.append(f"source_pin_mismatch:{name}")

    coverage_checks = []
    windows = {str(window["id"]): window for window in config["windows"]}
    for window_id, manifest in receipt["input_manifests"].items():
        window = windows[window_id]
        start = date.fromisoformat(str(window["evaluation_start"]))
        end = date.fromisoformat(str(window["evaluation_end_exclusive"]))
        by_symbol = {str(row["symbol"]): _dates_for_manifest_row(row) for row in manifest}
        expected = {session for session in by_symbol["SPY"] if start <= date.fromisoformat(session) < end}
        for row in manifest:
            symbol = str(row["symbol"])
            observed = by_symbol[symbol].intersection(expected)
            coverage = len(observed) / max(1, len(expected))
            missing = sorted(expected - observed)
            coverage_checks.append(
                {
                    "window": window_id,
                    "symbol": symbol,
                    "expected_sessions": len(expected),
                    "observed_sessions": len(observed),
                    "coverage_pct": coverage * 100.0,
                    "missing_session_count": len(missing),
                    "first_missing_sessions": missing[:5],
                    "ok": coverage >= 0.95,
                }
            )

    stress_checks = []
    grouped: dict[tuple[str, str], dict[float, float]] = {}
    for row in receipt["results"]:
        grouped.setdefault((str(row["window"]), str(row["arm"])), {})[float(row["cost_bps_per_side"])] = float(row["summary"]["return_pct"])
    for (window, arm), values in grouped.items():
        costs = sorted(values)
        ok = all(values[right] <= values[left] + 1e-9 for left, right in zip(costs, costs[1:]))
        stress_checks.append({"window": window, "arm": arm, "ok": ok, "returns_by_cost": values})
        if not ok:
            all_issues.append(f"cost_stress_nonmonotonic:{window}:{arm}")

    critical_caveats = [
        "survivorship_bias_unresolved",
        "authoritative_xnys_ledger_unpinned",
        "corporate_actions_and_delistings_unpinned",
        "daily_exit_proxy_not_intraday_live_parity",
        "broker_cost_calibration_unpinned",
    ]
    invariant_pass = not all_issues and all(row["ok"] for row in result_checks + pin_checks + stress_checks)
    validation = {
        "schema_id": "alpaca_honest_diagnostic_validation_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "receipt_path": str(receipt_path.relative_to(ROOT)),
        "receipt_sha256": _sha256(receipt_path),
        "independent_invariants_pass": invariant_pass,
        "data_quality_rating": "NEEDS_REVISION",
        "promotion_ready": False,
        "status": "PASS_INVARIANTS_WITH_CRITICAL_DATA_CAVEATS" if invariant_pass else "FAIL_INVARIANTS",
        "result_checks": result_checks,
        "source_pin_checks": pin_checks,
        "cost_stress_checks": stress_checks,
        "coverage_checks": coverage_checks,
        "coverage_below_95pct": [row for row in coverage_checks if not row["ok"]],
        "critical_caveats": critical_caveats,
        "issues": sorted(set(all_issues)),
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = [
        "# Alpaca honest diagnostic validation",
        "",
        f"- invariant status: `{validation['status']}`",
        f"- data quality: `{validation['data_quality_rating']}`",
        "- promotion ready: `false`",
        f"- result checks: `{sum(row['ok'] for row in result_checks)}/{len(result_checks)}`",
        f"- source pins: `{sum(row['ok'] for row in pin_checks)}/{len(pin_checks)}`",
        f"- cost-stress monotonicity: `{sum(row['ok'] for row in stress_checks)}/{len(stress_checks)}`",
        f"- symbols below 95% session coverage: `{len(validation['coverage_below_95pct'])}`",
        "",
        "Arithmetic and causal-order invariants passing does not remove the critical PIT, calendar, corporate-action, intraday-path, or cost-calibration blockers.",
    ]
    output.with_name("validation.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({key: validation[key] for key in ["status", "data_quality_rating", "promotion_ready"]}))
    print(f"validation={output.relative_to(ROOT)}")
    return 0 if invariant_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
