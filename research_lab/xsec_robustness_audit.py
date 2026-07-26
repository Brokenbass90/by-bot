#!/usr/bin/env python3
"""Bounded robustness audit for Claude's XSEC V4 candidate.

The original V4 result is retained unchanged.  This audit adds fixed,
non-optimizing stresses: total trading cost, maturity threshold, and random
universe dropout.  It also runs the stage-aware validator twice so a candidate
can be acceptable for risk-zero shadow while still being blocked from capital.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab import xsec_eventfilter as model
from research_lab.validator import validate


def _run(
    symbols: list[str],
    *,
    total_cost_bps: float,
    event_noise: bool = True,
    market_stress: bool = True,
) -> tuple[list[float], list[list[float]], dict]:
    previous_mature = model.mature
    previous_maker = model.MAKER
    previous_taker = model.TAKER
    try:
        model.mature = list(symbols)
        # build() subtracts 2*MAKER + 2*TAKER.  Splitting the requested total
        # equally preserves the exact total friction without pretending a fill
        # composition that has not yet been measured.
        per_component = total_cost_bps / 4.0 / 10_000.0
        model.MAKER = per_component
        model.TAKER = per_component
        phases = [
            model.vt(model.build(symbols, 46 + offset, event_noise, market_stress))
            for offset in (0, 1, 2)
        ]
        size = min(len(phase) for phase in phases)
        combined = [
            sum(phase[index] for phase in phases) / len(phases)
            for index in range(size)
        ]
        metrics = model.M(combined)
        metrics["n_rebalances"] = len(combined)
        metrics["symbols"] = len(symbols)
        metrics["total_cost_bps"] = total_cost_bps
        return combined, phases, metrics
    finally:
        model.mature = previous_mature
        model.MAKER = previous_maker
        model.TAKER = previous_taker


def _checks(report) -> list[dict]:
    return [
        {
            "name": check.name,
            "passed": check.passed,
            "severity": check.severity,
            "detail": check.detail,
        }
        for check in report.checks
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="reports/research/xsec_v4_robustness_audit_20260726.json",
    )
    args = parser.parse_args()

    maturity_thresholds = (180, 270, 390, 540)
    cost_scenarios = (8.0, 15.0, 22.0, 30.0)
    base_symbols = sorted(
        symbol for symbol in model.px if len(model.px[symbol]) >= 390
    )

    baseline_returns, baseline_phases, baseline = _run(
        base_symbols, total_cost_bps=15.0
    )
    costs = []
    for cost_bps in cost_scenarios:
        _, _, metrics = _run(base_symbols, total_cost_bps=cost_bps)
        costs.append(metrics)

    maturity = []
    for threshold in maturity_thresholds:
        symbols = sorted(
            symbol for symbol in model.px if len(model.px[symbol]) >= threshold
        )
        if len(symbols) < model.MIN_UNIVERSE if hasattr(model, "MIN_UNIVERSE") else len(symbols) < 14:
            maturity.append({
                "maturity_days": threshold,
                "symbols": len(symbols),
                "status": "insufficient_universe",
            })
            continue
        _, _, metrics = _run(symbols, total_cost_bps=15.0)
        metrics["maturity_days"] = threshold
        maturity.append(metrics)

    dropout = []
    for seed in (11, 23, 47):
        rng = random.Random(seed)
        kept = [
            symbol for symbol in base_symbols if rng.random() >= 0.20
        ]
        if len(kept) < 14:
            continue
        _, _, metrics = _run(kept, total_cost_bps=15.0)
        metrics["seed"] = seed
        metrics["dropout_fraction"] = 0.20
        dropout.append(metrics)

    shared_meta = {
        "windows_overlap": False,
        "posthoc_thresholds": "inherited maturity threshold 390d",
        "universe_includes_delisted": False,
        "taker_bps": 5.5,
    }
    research_report = validate(
        returns=baseline_returns,
        meta={**shared_meta, "promotion_stage": "research"},
        phases=baseline_phases,
        min_sharpe=2.19,
    )
    capital_report = validate(
        returns=baseline_returns,
        meta={
            **shared_meta,
            "promotion_stage": "capital",
            "out_of_sample": False,
            "slippage_modelled": False,
            "execution_parity": False,
        },
        phases=baseline_phases,
        min_sharpe=2.19,
    )

    payload = {
        "schema_id": "xsec_v4_robustness_audit_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "baseline": baseline,
        "cost_sensitivity": costs,
        "maturity_sensitivity": maturity,
        "universe_dropout_sensitivity": dropout,
        "validation": {
            "research_ok": research_report.ok,
            "research_checks": _checks(research_report),
            "capital_ok": capital_report.ok,
            "capital_checks": _checks(capital_report),
        },
        "promotion": "SHADOW",
        "binding_reason": (
            "Risk-zero shadow is allowed, but capital remains blocked by "
            "survivor-only prices, inherited maturity threshold, absent "
            "independent OOS, unmeasured slippage, and no execution parity."
        ),
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    print(
        f"baseline symbols={baseline['symbols']} n={baseline['n_rebalances']} "
        f"total={baseline['tot']}% DD={baseline['dd']}% Sharpe={baseline['sh']}"
    )
    for row in costs:
        print(
            f"cost={row['total_cost_bps']:>4.1f}bps total={row['tot']:>5}% "
            f"DD={row['dd']:>4}% Sharpe={row['sh']}"
        )
    for row in maturity:
        print(
            f"maturity={row['maturity_days']}d symbols={row['symbols']} "
            f"total={row.get('tot')} Sharpe={row.get('sh')}"
        )
    for row in dropout:
        print(
            f"drop20 seed={row['seed']} symbols={row['symbols']} "
            f"total={row['tot']} Sharpe={row['sh']}"
        )
    print(
        f"research_ok={research_report.ok} capital_ok={capital_report.ok} "
        f"out={output.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
