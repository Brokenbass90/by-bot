#!/usr/bin/env python3
"""Fail-closed validation for the cross-market strategy promotion queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = ROOT / "configs" / "research" / "strategy_promotion_queue_20260730.json"
ALLOWED_DATA_QUALITY = {"HIGH", "MEDIUM", "LOW", "BLOCKED_DATA"}
ALLOWED_STAGES = {
    "risk_zero_shadow",
    "queued_preregistration",
    "queued_causal_backtest",
    "queued_integration",
    "queued_data_collection",
    "queued_data_probe",
    "queued_design",
    "queued_cost_validation",
    "blocked_data",
    "terminal_fail",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_queue(payload: dict[str, Any]) -> None:
    _require(payload.get("schema_id") == "strategy_promotion_queue_v1", "wrong schema_id")
    _require(payload.get("research_only") is True, "queue must be research_only")
    _require(payload.get("capital_authorized") is False, "queue cannot authorize capital")

    wip = payload.get("wip")
    _require(isinstance(wip, dict), "wip must be an object")
    max_wip = wip.get("maximum_concurrent_research_supervisors")
    active = wip.get("active")
    _require(isinstance(max_wip, int) and max_wip >= 1, "invalid WIP maximum")
    _require(isinstance(active, list), "wip.active must be a list")
    _require(len(active) <= max_wip, "active research exceeds WIP maximum")
    _require(len(active) == len(set(active)), "duplicate active supervisor")

    all_ids: set[str] = set()
    for queue_name in ("crypto_queue", "fx_cfd_queue"):
        rows = payload.get(queue_name)
        _require(isinstance(rows, list) and rows, f"{queue_name} must be non-empty")
        ranks: list[int] = []
        for row in rows:
            _require(isinstance(row, dict), f"{queue_name} row must be an object")
            strategy_id = row.get("id")
            rank = row.get("rank")
            _require(isinstance(strategy_id, str) and strategy_id, f"{queue_name} missing id")
            _require(strategy_id not in all_ids, f"duplicate strategy id: {strategy_id}")
            all_ids.add(strategy_id)
            _require(isinstance(rank, int) and rank >= 1, f"{strategy_id}: invalid rank")
            ranks.append(rank)
            _require(row.get("stage") in ALLOWED_STAGES, f"{strategy_id}: invalid stage")
            _require(
                row.get("data_quality") in ALLOWED_DATA_QUALITY,
                f"{strategy_id}: invalid data_quality",
            )
            for required in ("family", "portfolio_role", "binding_risk", "next_artifact"):
                _require(bool(row.get(required)), f"{strategy_id}: missing {required}")
            gate_key = "first_money_gate" if queue_name == "crypto_queue" else "first_demo_gate"
            _require(bool(row.get(gate_key)), f"{strategy_id}: missing {gate_key}")

    for queue_name in ("crypto_queue", "fx_cfd_queue"):
        ranks = [row["rank"] for row in payload[queue_name]]
        _require(ranks == sorted(ranks), f"{queue_name} ranks must be sorted")
        _require(len(ranks) == len(set(ranks)), f"{queue_name} has duplicate ranks")

    launch_rows = payload.get("next_launch_order")
    _require(isinstance(launch_rows, list) and launch_rows, "next_launch_order must be non-empty")
    for row in launch_rows:
        _require(row.get("launch") in all_ids, f"unknown launch id: {row.get('launch')}")
        _require(bool(row.get("when")), f"launch {row.get('launch')} missing condition")

    invariants = payload.get("live_invariants", {})
    _require(
        invariants.get("att1_risk_signal_and_universe_unchanged") is True,
        "ATT1 invariant must remain explicit",
    )
    _require(invariants.get("ai_may_raise_live_risk") is False, "AI risk authority forbidden")
    _require(
        invariants.get("new_money_sleeve_requires_deploy_receipt") is True,
        "new money sleeves require deploy receipt",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", nargs="?", type=Path, default=DEFAULT_QUEUE)
    args = parser.parse_args()
    path = args.queue if args.queue.is_absolute() else ROOT / args.queue
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_queue(payload)
    print(
        json.dumps(
            {
                "status": "PASS",
                "queue": str(path.relative_to(ROOT)),
                "crypto_candidates": len(payload["crypto_queue"]),
                "fx_cfd_candidates": len(payload["fx_cfd_queue"]),
                "active_wip": len(payload["wip"]["active"]),
                "maximum_wip": payload["wip"]["maximum_concurrent_research_supervisors"],
                "capital_authorized": payload["capital_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
