#!/usr/bin/env python3
"""Build a compact, reproducible evidence receipt for frequent crypto rehab.

The script is read-only with respect to trading state.  It summarizes frozen
research artifacts and never calls a broker or exchange.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.DictReader(handle))


def _f(value: Any) -> float:
    return float(value)


def build_receipt(root: Path = ROOT) -> dict[str, Any]:
    pump_path = (
        root
        / "reports/research/pump_exhaustion_unwind_short_v1_20260713_strict_gate/metrics.json"
    )
    pump = _json(pump_path)
    pump_metrics = pump["metrics"]

    run_root = root / "backtest_runs"
    exact_runs = {
        "range_short_base": "portfolio_20260711_143238_fc_20260711_ars1_short_control_adx0_360d_base_20260711_112429",
        "range_short_stress": "portfolio_20260711_143421_fc_20260711_ars1_short_control_adx0_360d_stress_20260711_112429",
        "range_short_adx25_stress": "portfolio_20260711_143755_fc_20260711_ars1_short_adx25_360d_stress_20260711_112429",
        "range_long_base": "portfolio_20260711_142458_fc_20260711_ars1_long_control_adx0_360d_base_20260711_112429",
        "bounce_nodesc_stress": "portfolio_20260711_145328_fc_20260711_asb2_nodescending_360d_stress_20260711_112429",
    }
    summaries = {
        name: _summary(run_root / dirname / "summary.csv")
        for name, dirname in exact_runs.items()
    }

    sloped_path = root / "research_lab/results/sloped_v1.jsonl"
    sloped_rows = [
        json.loads(line)
        for line in sloped_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sloped_unique = {row["key"]: row for row in sloped_rows}

    sweep_path = (
        root
        / "reports/research/crypto_level_memory_sweep_reclaim_20260707_20260707_125758/grid.csv"
    )
    with sweep_path.open(newline="", encoding="utf-8") as handle:
        sweep_rows = list(csv.DictReader(handle))
    sweep_passes = [row for row in sweep_rows if int(row["pass_exploration"]) == 1]
    repaired_sweep_path = (
        root
        / "reports/research/level_memory_sweep_reclaim_v2_cost_repair_20260727/grid.csv"
    )
    with repaired_sweep_path.open(newline="", encoding="utf-8") as handle:
        repaired_sweep = next(csv.DictReader(handle))

    return {
        "schema": "frequent_crypto_rehab_evidence_v2",
        "research_only": True,
        "live_or_broker_calls": False,
        "sources": {
            "pump": str(pump_path.relative_to(root)),
            "range_and_bounce": [f"backtest_runs/{name}/summary.csv" for name in exact_runs.values()],
            "sloped": str(sloped_path.relative_to(root)),
            "sweep": str(sweep_path.relative_to(root)),
            "sweep_cost_repair": str(repaired_sweep_path.relative_to(root)),
        },
        "findings": {
            "pump_exhaustion_unwind_short_v1": {
                "verdict": pump["verdict"],
                "trades": int(pump_metrics["base"]["trades"]),
                "base_profit_factor": _f(pump_metrics["base"]["profit_factor"]),
                "stress_profit_factor": _f(pump_metrics["stress"]["profit_factor"]),
                "holdout_trades": int(pump_metrics["holdout_stress"]["trades"]),
                "positive_folds": int(pump_metrics["positive_folds"]),
                "failed_gates": list(pump["failed_gates"]),
                "decision": "PROSPECTIVE_REHAB_PRIORITY_1",
            },
            "range_scalp": {
                "short_base_trades": int(summaries["range_short_base"]["trades"]),
                "short_base_profit_factor": _f(summaries["range_short_base"]["profit_factor"]),
                "short_stress_profit_factor": _f(summaries["range_short_stress"]["profit_factor"]),
                "short_adx25_stress_profit_factor": _f(
                    summaries["range_short_adx25_stress"]["profit_factor"]
                ),
                "long_base_profit_factor": _f(summaries["range_long_base"]["profit_factor"]),
                "decision": "DO_NOT_PROMOTE_OLD_RANGE",
            },
            "generic_support_bounce": {
                "stress_trades": int(summaries["bounce_nodesc_stress"]["trades"]),
                "stress_profit_factor": _f(
                    summaries["bounce_nodesc_stress"]["profit_factor"]
                ),
                "decision": "RETIRE_TOUCH_BOUNCE_KEEP_SWEEP_RECLAIM_HYPOTHESIS",
            },
            "level_memory_sweep_reclaim": {
                "legacy_grid_rows": len(sweep_rows),
                "legacy_exploration_pass_rows": len(sweep_passes),
                "legacy_cost_contract_valid": False,
                "cost_repair_trades": int(repaired_sweep["trades"]),
                "cost_repair_net_r": _f(repaired_sweep["net_r"]),
                "cost_repair_profit_factor": _f(repaired_sweep["pf"]),
                "cost_repair_positive_folds": int(repaired_sweep["folds_pos"]),
                "decision": "NO_PROMOTION_REDESIGN_CAUSAL_LEVEL_AND_STRUCTURE",
            },
            "sloped_break_retest_v1": {
                "unique_parameter_cases": len(sloped_unique),
                "passed_cases": sum(bool(row.get("is_pass")) for row in sloped_unique.values()),
                "decision": "SUPERSEDE_WITH_EVENT_TRIGGERED_V2",
            },
            "elder": {
                "canonical_trades": 383,
                "canonical_profit_factor": 0.84,
                "positive_folds": 1,
                "total_folds": 4,
                "decision": "FILTER_ABLATION_ONLY",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "reports/research/frequent_crypto_rehab_v2_20260727.json"),
    )
    args = parser.parse_args()
    receipt = build_receipt()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
