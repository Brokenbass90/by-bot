#!/usr/bin/env python3
"""Bounded causal repair of Alpaca regime gate plus calendar exit."""
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
        default="configs/preregistered/alpaca_adaptive_regime_exit_repair_20260728.json",
    )
    parser.add_argument(
        "--historical-prereg",
        default="configs/preregistered/alpaca_adaptive_historical_proxy_20260728.json",
    )
    parser.add_argument(
        "--out",
        default="reports/research/alpaca_adaptive_regime_exit_repair_20260728/receipt.json",
    )
    args = parser.parse_args()
    prereg_path = ROOT / args.prereg
    historical_path = ROOT / args.historical_prereg
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    historical = json.loads(historical_path.read_text(encoding="utf-8"))
    windows = {row["id"]: row for row in historical["windows"]}
    contract = SharedExitContract(**prereg["fixed"]["exit"])

    rows = []
    for regime_mode in prereg["regime_arms"]:
        for window_id in prereg["fixed"]["windows"]:
            for cost in prereg["fixed"]["cost_bps_per_side"]:
                summary, decisions, _manifest = _run_window(
                    windows[window_id],
                    cost_bps_per_side=float(cost),
                    use_gate=True,
                    target_alloc_pct=float(prereg["fixed"]["target_alloc_pct"]),
                    max_positions=int(prereg["fixed"]["max_positions"]),
                    exit_contract=contract,
                    regime_mode=regime_mode,
                )
                rows.append({
                    "regime_arm": regime_mode,
                    "window": window_id,
                    "cost_bps_per_side": cost,
                    "summary": summary,
                    "decisions": decisions,
                })
                print(
                    f"{regime_mode} {window_id} cost={cost}: "
                    f"return={summary['return_pct']:+.2f}% "
                    f"DD={summary['monthly_endpoint_drawdown_pct']:.2f}% "
                    f"red={summary['red_months']}/{summary['months']}"
                )

    stressed = [row for row in rows if float(row["cost_bps_per_side"]) == 10.0]
    baseline_recent = next(
        row["summary"]["return_pct"] for row in stressed
        if row["regime_arm"] == "baseline_sma200"
        and row["window"] == "recent_2025_2026_survivor_proxy"
    )
    arm_verdicts = {}
    for arm in prereg["regime_arms"]:
        arm_rows = [row for row in stressed if row["regime_arm"] == arm]
        recent = next(
            row["summary"]["return_pct"] for row in arm_rows
            if row["window"] == "recent_2025_2026_survivor_proxy"
        )
        passed = (
            all(row["summary"]["return_pct"] > 0 for row in arm_rows)
            and all(row["summary"]["monthly_endpoint_drawdown_pct"] <= 10.0 for row in arm_rows)
            and recent >= baseline_recent * 0.75
        )
        arm_verdicts[arm] = {
            "passed": passed,
            "recent_return_pct": recent,
            "recent_haircut_vs_baseline_fraction": (
                1.0 - recent / baseline_recent if baseline_recent else None
            ),
        }
    passed = [arm for arm, verdict in arm_verdicts.items() if verdict["passed"]]
    receipt = {
        "schema_id": "alpaca_adaptive_regime_exit_repair_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "safe_hold_changed": False,
        "broker_or_network_calls": False,
        "prereg_sha256": _sha256(prereg_path),
        "historical_prereg_sha256": _sha256(historical_path),
        "results": rows,
        "arm_verdicts": arm_verdicts,
        "candidate_arms": passed,
        "verdict": "REPAIR_CANDIDATE" if passed else "NO_GO_THIS_REPAIR",
        "promotion": "RESEARCH_ONLY",
        "next_gate": "PIT plus untouched exact-parity replay; no live entries",
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(f"verdict={receipt['verdict']} candidate_arms={','.join(passed) or '-'}")
    print(f"receipt={output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
