"""Descriptive-only ROI sample builder for receipt-complete v3 cycles."""

from __future__ import annotations

import math
import statistics
from typing import Any


def build_roi(state: dict[str, Any]) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    exclusions: dict[str, int] = {}
    for position in state.get("positions") or []:
        reason: str | None = None
        if position.get("model_version") != "settlement_execution_v3":
            reason = "foreign_model_version"
        elif position.get("status") != "closed_complete":
            reason = str(position.get("status") or "unknown_status")
        elif position.get("exit_execution_valid") is not True:
            reason = "exit_not_executable"
        elif position.get("settlement_status") != "complete":
            reason = str(position.get("settlement_status") or "settlement_unknown")
        elif position.get("pending_settlements"):
            reason = "pending_settlement_receipts"
        elif position.get("net_pnl_pct_total_deployed_capital") is None:
            reason = "final_pnl_unknown"
        else:
            try:
                value = float(position["net_pnl_pct_total_deployed_capital"])
            except (TypeError, ValueError):
                reason = "final_pnl_not_numeric"
            else:
                if not math.isfinite(value):
                    reason = "final_pnl_not_finite"
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        eligible.append(position)

    returns = [
        float(row["net_pnl_pct_total_deployed_capital"]) for row in eligible
    ]
    return {
        "schema_version": "settlement_execution_v3_roi_v1",
        "model_version": "settlement_execution_v3",
        "status": "research_sample_only",
        "edge_proven": False,
        "ready_for_live": False,
        "monetary_projection": None,
        "eligibility_contract": {
            "actual_public_funding_receipts_required": True,
            "executable_exit_required": True,
            "pending_or_missing_receipts_excluded": True,
            "primary_denominator": "total_deployed_virtual_capital",
        },
        "eligible_closed_cycles": len(eligible),
        "excluded_cycles": len(state.get("positions") or []) - len(eligible),
        "exclusion_counters": dict(sorted(exclusions.items())),
        "sample": {
            "mean_return_pct_total_deployed_capital": statistics.mean(returns)
            if returns
            else None,
            "median_return_pct_total_deployed_capital": statistics.median(returns)
            if returns
            else None,
            "wins": sum(value > 0 for value in returns),
            "losses": sum(value < 0 for value in returns),
            "flat": sum(value == 0 for value in returns),
        },
        "limitations": [
            (
                "No private account fee receipts; fee contracts are preregistered "
                "conservative assumptions."
            ),
            (
                "No orders, fills, transfers, margin, liquidation, or legging are "
                "simulated beyond public book walks."
            ),
            (
                "No independence-adjusted inference or forward monetary projection "
                "is produced by this skeleton."
            ),
        ],
        "metrics": {
            "eligible_count": len(eligible),
            "excluded_count": len(state.get("positions") or []) - len(eligible),
        },
    }
