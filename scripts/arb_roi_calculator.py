#!/usr/bin/env python3
"""Estimate cross-exchange funding ROI from closed conservative shadow cycles.

This report intentionally refuses to project ROI from a current funding spread
or from open shadow positions. A projection becomes available only after the
configured minimum number of cycles has closed under the current execution
model, with fees, executable prices, and settled funding already included.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "runtime" / "arb" / "cross_exchange_funding_shadow.json"
DEFAULT_OUT = ROOT / "runtime" / "arb_roi_estimate.json"
REQUIRED_MODEL_VERSION = "settlement_execution_v2"
COHORT_CURRENT_MODEL = "current_model_all"
COHORT_EXPLICIT_VALIDATION = "explicit_validation_v1"
HOURS_PER_MONTH = 24.0 * 30.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cycle_hold_hours(cycle: dict[str, Any]) -> float:
    last_update = cycle.get("last_update") or {}
    age_hours = _f(last_update.get("age_hours"))
    if age_hours > 0:
        return age_hours
    opened = _f(cycle.get("opened_at_epoch"))
    closed = _parse_utc(cycle.get("closed_at_utc"))
    if opened > 0 and closed:
        return max(0.0, (closed.timestamp() - opened) / 3600.0)
    return max(0.0, _f(cycle.get("hold_hours")))


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return ordered[lower]
    weight = pos - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _next_expected_close_utc(state: dict[str, Any]) -> str | None:
    candidates: list[float] = []
    for cycle in state.get("open") or []:
        opened = _f(cycle.get("opened_at_epoch"))
        hold_hours = _f(cycle.get("hold_hours"))
        if opened > 0 and hold_hours > 0:
            candidates.append(opened + hold_hours * 3600.0)
    if not candidates:
        return None
    return datetime.fromtimestamp(min(candidates), timezone.utc).isoformat()


def _has_explicit_validation_evidence(cycle: dict[str, Any]) -> bool:
    """Identify cycles closed under the repaired explicit-validation contract.

    Older cycles treated absence from the validator's top-N output as a failed
    validation.  The repaired lifecycle stores both `current_observed` and
    `current_validated` on every markout, so the cohort can be selected without
    relying on a mutable timestamp or a symbol allowlist.
    """
    last_update = cycle.get("last_update")
    return (
        isinstance(last_update, dict)
        and "current_observed" in last_update
        and "current_validated" in last_update
    )


def _eligible_closed_cycles(
    state: dict[str, Any],
    *,
    cohort: str = COHORT_CURRENT_MODEL,
) -> list[dict[str, Any]]:
    eligible = []
    for cycle in state.get("closed") or []:
        if cycle.get("model_version") != REQUIRED_MODEL_VERSION:
            continue
        if (
            cohort == COHORT_EXPLICIT_VALIDATION
            and not _has_explicit_validation_evidence(cycle)
        ):
            continue
        result = cycle.get("final_shadow_pct_total_capital")
        try:
            result_float = float(result)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(result_float):
            continue
        eligible.append(cycle)
    return eligible


def _scenario_rows(
    *,
    capitals: list[float],
    monthly_return_pct_deployed: float,
    max_open: int,
    notional_per_leg: float,
) -> list[dict[str, Any]]:
    capacity = max(0.0, float(max_open) * float(notional_per_leg) * 2.0)
    rows = []
    for capital in capitals:
        requested = max(0.0, float(capital))
        deployed = min(requested, capacity) if capacity > 0 else 0.0
        monthly_usd = deployed * monthly_return_pct_deployed / 100.0
        rows.append(
            {
                "capital_total_usd": round(requested, 2),
                "capital_deployed_usd": round(deployed, 2),
                "capital_idle_usd": round(max(0.0, requested - deployed), 2),
                "monthly_pnl_usd": round(monthly_usd, 4),
                "monthly_return_pct_total_capital": round(
                    (monthly_usd / requested * 100.0) if requested > 0 else 0.0,
                    4,
                ),
            }
        )
    return rows


def build_report(
    state: dict[str, Any],
    *,
    capitals: list[float],
    min_closed_cycles: int = 10,
    cohort: str = COHORT_CURRENT_MODEL,
    require_positive_distribution: bool = True,
) -> dict[str, Any]:
    if cohort not in {COHORT_CURRENT_MODEL, COHORT_EXPLICIT_VALIDATION}:
        raise ValueError(f"unsupported cohort: {cohort}")
    all_current_model = _eligible_closed_cycles(
        state,
        cohort=COHORT_CURRENT_MODEL,
    )
    closed = _eligible_closed_cycles(state, cohort=cohort)
    returns = [_f(cycle.get("final_shadow_pct_total_capital")) for cycle in closed]
    hold_hours = [hours for cycle in closed if (hours := _cycle_hold_hours(cycle)) > 0]
    settings = state.get("settings") or {}
    max_open = int(_f(settings.get("max_open"), 0.0))
    notional_per_leg = _f(settings.get("notional_usd_per_leg"))

    sample = {
        "cohort": cohort,
        "closed_cycles": len(closed),
        "excluded_current_model_cycles": len(all_current_model) - len(closed),
        "open_cycles": len(state.get("open") or []),
        "wins": sum(1 for value in returns if value > 0),
        "losses": sum(1 for value in returns if value < 0),
        "flat": sum(1 for value in returns if value == 0),
        "win_rate": round(
            sum(1 for value in returns if value > 0) / len(returns), 4
        ) if returns else None,
        "mean_return_pct_total_capital_per_cycle": round(statistics.mean(returns), 6)
        if returns else None,
        "median_return_pct_total_capital_per_cycle": round(statistics.median(returns), 6)
        if returns else None,
        "p25_return_pct_total_capital_per_cycle": round(_percentile(returns, 0.25), 6)
        if returns else None,
        "worst_return_pct_total_capital_per_cycle": round(min(returns), 6)
        if returns else None,
        "best_return_pct_total_capital_per_cycle": round(max(returns), 6)
        if returns else None,
        "average_hold_hours": round(statistics.mean(hold_hours), 4) if hold_hours else None,
        "next_expected_close_utc": _next_expected_close_utc(state),
    }

    enough_cycles = len(closed) >= max(1, int(min_closed_cycles)) and bool(hold_hours)
    planning_return = _percentile(returns, 0.25) if enough_cycles else 0.0
    positive_distribution = planning_return > 0.0
    sufficient = enough_cycles and (
        positive_distribution or not require_positive_distribution
    )
    average_hold = statistics.mean(hold_hours) if hold_hours else 0.0
    monthly_return_deployed = (
        planning_return * (HOURS_PER_MONTH / average_hold)
        if sufficient and average_hold > 0
        else 0.0
    )

    report = {
        "generated_at_utc": _utc_now(),
        "status": (
            "projection_available"
            if sufficient
            else (
                "non_positive_executable_distribution"
                if enough_cycles and require_positive_distribution
                else "insufficient_closed_cycles"
            )
        ),
        "model_version_required": REQUIRED_MODEL_VERSION,
        "model_version_seen": state.get("model_version"),
        "cohort_required": cohort,
        "minimum_closed_cycles": max(1, int(min_closed_cycles)),
        "positive_distribution_required": bool(require_positive_distribution),
        "sample": sample,
        "projection": None,
        "reason": None,
    }
    if not sufficient:
        if not enough_cycles:
            report["reason"] = (
                f"need at least {max(1, int(min_closed_cycles))} closed "
                f"{REQUIRED_MODEL_VERSION} cycles in cohort {cohort}; "
                f"found {len(closed)}"
            )
        else:
            report["reason"] = (
                "closed-cycle count passed, but the executable return "
                f"distribution is not positive: p25={planning_return:.6f}%"
            )
        return report

    report["projection"] = {
        "method": "observed_closed_cycles_p25",
        "planning_cycle_return_pct_total_capital": round(planning_return, 6),
        "monthly_return_pct_deployed_capital": round(monthly_return_deployed, 6),
        "annualized_simple_return_pct_deployed_capital": round(
            monthly_return_deployed * 12.0, 6
        ),
        "capacity_usd": round(max_open * notional_per_leg * 2.0, 2),
        "scenarios": _scenario_rows(
            capitals=capitals,
            monthly_return_pct_deployed=monthly_return_deployed,
            max_open=max_open,
            notional_per_leg=notional_per_leg,
        ),
        "warning": (
            "Planning estimate uses the observed 25th-percentile closed-cycle "
            "return. It is not a guarantee and remains sensitive to crowding, "
            "latency, fees, liquidity, and exchange risk."
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate funding-arbitrage ROI from closed conservative shadow cycles"
    )
    parser.add_argument(
        "--state-json",
        default=str(DEFAULT_STATE.relative_to(ROOT)),
        help="Shadow state path relative to repository root, or an absolute path",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUT.relative_to(ROOT)),
        help="Report path relative to repository root, or an absolute path",
    )
    parser.add_argument(
        "--capital",
        nargs="+",
        type=float,
        default=[200.0, 500.0, 1000.0, 2000.0, 5000.0],
        help="Capital scenarios in USD",
    )
    parser.add_argument(
        "--min-closed-cycles",
        type=int,
        default=20,
        help="Minimum current-model closed cycles required before projection",
    )
    parser.add_argument(
        "--cohort",
        choices=[COHORT_CURRENT_MODEL, COHORT_EXPLICIT_VALIDATION],
        default=COHORT_EXPLICIT_VALIDATION,
        help=(
            "Closed-cycle cohort. The default excludes cycles created before "
            "the explicit validator-evidence repair."
        ),
    )
    parser.add_argument(
        "--allow-non-positive-distribution",
        action="store_true",
        help="Diagnostic only: allow a projection even when observed p25 <= 0",
    )
    args = parser.parse_args()

    state_path = Path(args.state_json)
    if not state_path.is_absolute():
        state_path = ROOT / state_path
    output_path = Path(args.output_json)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    state = _load_json(state_path)
    report = build_report(
        state,
        capitals=args.capital,
        min_closed_cycles=args.min_closed_cycles,
        cohort=args.cohort,
        require_positive_distribution=not args.allow_non_positive_distribution,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "projection_available" else 2


if __name__ == "__main__":
    sys.exit(main())
