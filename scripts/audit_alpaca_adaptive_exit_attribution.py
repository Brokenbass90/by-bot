#!/usr/bin/env python3
"""Attribute Alpaca Adaptive V1 failure to selector versus exit mechanics."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.alpaca_exact_parity_contract import SharedExitContract  # noqa: E402
from scripts.audit_alpaca_adaptive_historical_proxy import _run_window  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prereg",
        default="configs/preregistered/alpaca_adaptive_exit_attribution_20260728.json",
    )
    parser.add_argument(
        "--parent-prereg",
        default="configs/preregistered/alpaca_adaptive_historical_proxy_20260728.json",
    )
    parser.add_argument(
        "--out",
        default="reports/research/alpaca_adaptive_exit_attribution_20260728/receipt.json",
    )
    args = parser.parse_args()
    prereg_path = ROOT / args.prereg
    parent_path = ROOT / args.parent_prereg
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    windows = {row["id"]: row for row in parent["windows"]}

    rows = []
    for window_id in prereg["fixed"]["windows"]:
        for cost in prereg["fixed"]["cost_bps_per_side"]:
            for arm, values in prereg["exit_arms"].items():
                contract = SharedExitContract(**values)
                summary, decisions, _manifest = _run_window(
                    windows[window_id],
                    cost_bps_per_side=float(cost),
                    use_gate=True,
                    target_alloc_pct=float(prereg["fixed"]["target_alloc_pct"]),
                    max_positions=int(prereg["fixed"]["max_positions"]),
                    exit_contract=contract,
                )
                rows.append({
                    "window": window_id,
                    "cost_bps_per_side": cost,
                    "exit_arm": arm,
                    "summary": summary,
                    "decisions": decisions,
                })
                print(
                    f"{window_id} {arm} cost={cost}: "
                    f"return={summary['return_pct']:+.2f}% "
                    f"PF={summary['profit_factor']:.3f} "
                    f"DD={summary['monthly_endpoint_drawdown_pct']:.2f}%"
                )

    base = [row for row in rows if float(row["cost_bps_per_side"]) == 5.0]
    combined = {
        arm: sum(
            row["summary"]["return_pct"]
            for row in base if row["exit_arm"] == arm
        )
        for arm in prereg["exit_arms"]
    }
    hold = combined["calendar_hold_22"]
    shared = combined["shared_default"]
    wide_rows = [row for row in base if row["exit_arm"] == "wide_same_shape"]
    wide_candidate = all(
        row["summary"]["return_pct"] > 0
        and row["summary"]["monthly_endpoint_drawdown_pct"] <= 15.0
        for row in wide_rows
    )
    if hold <= 0:
        verdict = "SELECTOR_BINDING"
    elif shared <= 0:
        verdict = "EXIT_BINDING"
    else:
        verdict = "NO_SINGLE_BINDING_DEFECT"
    receipt = {
        "schema_id": "alpaca_adaptive_exit_attribution_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "safe_hold_changed": False,
        "broker_or_network_calls": False,
        "prereg_sha256": _sha256(prereg_path),
        "parent_prereg_sha256": _sha256(parent_path),
        "results": rows,
        "combined_window_returns_pct_at_5bps": combined,
        "verdict": verdict,
        "wide_exit_candidate": wide_candidate,
        "promotion": "RESEARCH_ONLY",
        "capital_blockers": parent["interpretation"]["not_promotion_grade_because"],
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(f"verdict={verdict} wide_exit_candidate={wide_candidate}")
    print(f"receipt={output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
