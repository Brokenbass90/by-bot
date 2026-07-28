#!/usr/bin/env python3
"""Build a fail-closed status for the two event-driven crypto successors.

This is a local evidence aggregator. It does not fetch market data, calculate
new performance, tune thresholds, place orders, or mutate live risk.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_event_expansion_retest_long_v1_phase1 import (  # noqa: E402
    build_preflight,
)


PUMP_METRICS = (
    ROOT
    / "reports"
    / "research"
    / "pump_exhaustion_unwind_short_v1_20260713_strict_gate"
    / "metrics.json"
)
EVENT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "event_expansion_retest_long_v1_phase1_20260713.json"
)
EVENT_RUN_ROOT = (
    ROOT
    / "runtime"
    / "research"
    / "event_universe_v2r2_20260721_public1"
)
DEFAULT_OUT = (
    ROOT
    / "runtime"
    / "research"
    / "crypto_event_rehab_pair_status.json"
)


def _read_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def _iso_from_ms(value: Any) -> str | None:
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000.0, timezone.utc).isoformat()


def _receipt_has_scored_outcomes(receipt: Mapping[str, Any]) -> bool:
    """Accept both the legacy marker and the frozen scorer's current receipt."""
    if receipt.get("outcomes_scored") is True:
        return True
    if receipt.get("validation_status") != "passed":
        return False
    counts = receipt.get("status_counts_by_horizon")
    if not isinstance(counts, Mapping):
        return False
    return any(
        isinstance(row, Mapping) and int(row.get("scored") or 0) > 0
        for row in counts.values()
    )


def build_status(
    *,
    pump: Mapping[str, Any],
    event_preflight: Mapping[str, Any],
    latest_state: Mapping[str, Any],
    launch_receipt: Mapping[str, Any],
    label_receipts: list[Mapping[str, Any]],
) -> dict[str, Any]:
    pump_metrics = pump.get("metrics")
    if not isinstance(pump_metrics, Mapping):
        raise ValueError("pump metrics missing")
    base = pump_metrics.get("base")
    stress = pump_metrics.get("stress")
    holdout = pump_metrics.get("holdout_stress")
    if not all(isinstance(row, Mapping) for row in (base, stress, holdout)):
        raise ValueError("pump gate summary missing")

    blocker_codes = [
        str(row.get("code"))
        for row in event_preflight.get("blockers") or []
        if isinstance(row, Mapping)
    ]
    scored_receipts = [
        row
        for row in label_receipts
        if _receipt_has_scored_outcomes(row)
    ]
    source_finished = bool(scored_receipts)

    return {
        "schema": "crypto_event_rehab_pair_status_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "executable": False,
        "orders_or_risk_mutation": False,
        "parameter_tuning": False,
        "lanes": [
            {
                "strategy": "pump_exhaustion_unwind_short_v1",
                "side": "short_only",
                "status": "PROSPECTIVE_SAMPLE_REQUIRED",
                "historical_gate": {
                    "verdict": pump.get("verdict"),
                    "failed_gates": list(pump.get("failed_gates") or []),
                    "base": {
                        "trades": base.get("trades"),
                        "profit_factor": base.get("profit_factor"),
                        "return_pct": base.get("return_pct"),
                        "max_drawdown_pct": base.get("max_drawdown_pct"),
                    },
                    "stress": {
                        "trades": stress.get("trades"),
                        "profit_factor": stress.get("profit_factor"),
                        "return_pct": stress.get("return_pct"),
                        "max_drawdown_pct": stress.get("max_drawdown_pct"),
                    },
                    "holdout_stress": {
                        "trades": holdout.get("trades"),
                        "profit_factor": holdout.get("profit_factor"),
                        "net_r": holdout.get("net_r"),
                    },
                    "traded_symbols": pump_metrics.get("traded_symbols"),
                    "positive_symbols": pump_metrics.get("positive_symbols"),
                },
                "repair": (
                    "Keep the frozen exhaustion/CHOCH/failed-reclaim mechanics; "
                    "add genuinely post-window event-universe episodes instead "
                    "of retuning the revealed 39 trades."
                ),
            },
            {
                "strategy": "event_expansion_retest_long_v1",
                "side": "long_only",
                "status": event_preflight.get("status"),
                "integrity_pass": bool(
                    (event_preflight.get("identity") or {}).get("integrity_pass")
                ),
                "performance_permission": event_preflight.get(
                    "performance_permission"
                ),
                "live_permission": event_preflight.get("live_permission"),
                "remaining_blockers": blocker_codes,
                "remaining_blocker_count": len(blocker_codes),
                "repair": (
                    "Finish the single-owner performance/receipt runner and "
                    "materialize funding, external8, liquidity, metadata, and "
                    "same-window ATT1 evidence before opening results."
                ),
            },
        ],
        "prospective_discovery": {
            "collector": "event_universe_v2r2",
            "sequence": latest_state.get("sequence"),
            "latest_as_of_utc": _iso_from_ms(latest_state.get("as_of_ms")),
            "deadline_utc": _iso_from_ms(launch_receipt.get("deadline_at_ms")),
            "label_receipts_found": len(label_receipts),
            "successful_label_receipts_found": len(scored_receipts),
            "postrun_label_gate_complete": source_finished,
            "next_action": (
                "consume_frozen_labels_without_threshold_tuning"
                if source_finished
                else "wait_for_bounded_collector_then_run_frozen_label_scorer"
            ),
        },
        "portfolio_role": {
            "short_lane": "pump_exhaustion_unwind_short_v1",
            "long_lane": "event_expansion_retest_long_v1",
            "shared_discovery_only": "event_universe_v2r2",
            "statistics_must_remain_side_separated": True,
            "initial_risk": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-root", type=Path, default=EVENT_RUN_ROOT)
    args = parser.parse_args()

    pump = _read_mapping(PUMP_METRICS)
    config = _read_mapping(EVENT_CONFIG)
    event_preflight = build_preflight(config, ROOT)
    latest_state = _read_mapping(args.run_root / "latest_state.json")
    launch_receipt = _read_mapping(args.run_root / "launch_receipt_v2.json")
    receipt_paths = sorted(
        (ROOT / "reports" / "research" / "event_universe_v1_labels").glob(
            "event_universe_label_*.json"
        )
    )
    label_receipts = [_read_mapping(path) for path in receipt_paths]
    status = build_status(
        pump=pump,
        event_preflight=event_preflight,
        latest_state=latest_state,
        launch_receipt=launch_receipt,
        label_receipts=label_receipts,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
