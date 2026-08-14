from __future__ import annotations

import json
from pathlib import Path

from scripts.build_strategy_inventory import build_inventory


def test_inventory_keeps_liveness_separate_from_performance(tmp_path: Path) -> None:
    census = tmp_path / "census.json"
    manifest = tmp_path / "manifest.json"
    census.write_text(json.dumps({"demo": {"status": "ЖИВАЯ", "signals": 7, "exc": 0}}), encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "reference_counts": {"demo": 2},
                "monolith": {"wired_entry_handlers": ["try_demo_entry"], "enable_flags": ["ENABLE_DEMO_TRADING"]},
            }
        ),
        encoding="utf-8",
    )

    result = build_inventory(census, manifest)
    demo = next(row for row in result["strategies"] if row["name"] == "demo")

    assert demo["research_liveness_status"] == "ЖИВАЯ"
    assert demo["performance_status"] == "NOT_ESTABLISHED_BY_THIS_INVENTORY"
    assert demo["live_authority"] == "NOT_ESTABLISHED_BY_THIS_INVENTORY"
    assert result["summary"]["wired_entry_handler_count"] == 1
