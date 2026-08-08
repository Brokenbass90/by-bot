import json
import os
from pathlib import Path

from research_lab.negative_outcome_registry import collect_research_contours, collect_runtime_conversion, merge


def test_fresh_runtime_counters_are_diagnostic_not_profit_verdict(tmp_path: Path):
    path = tmp_path / "runtime" / "live_mirror" / "bot_heartbeat.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"runtime_counters": {
        "att1_try": 12,
        "att1_no_signal": 12,
        "att1_ns_touch": 9,
    }}), encoding="utf-8")
    os.utime(path, None)
    rows, coverage = collect_runtime_conversion(tmp_path)
    assert coverage["fresh"] is True
    assert len(rows) == 1
    assert rows[0]["strategy"] == "att1"
    assert rows[0]["safe_for_profit_verdict"] is False
    assert "touch" in rows[0]["detail"]


def test_stale_runtime_is_excluded(tmp_path: Path):
    path = tmp_path / "runtime" / "live_mirror" / "bot_heartbeat.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (1, 1))
    rows, coverage = collect_runtime_conversion(tmp_path)
    assert rows == []
    assert coverage["fresh"] is False


def test_merge_preserves_confirmed_status():
    row = {
        "id": "x", "source": "s", "strategy": "a", "phenotype": "p",
        "detail": "d", "evidence": "e", "scope": "q",
        "safe_for_profit_verdict": False, "severity": "medium",
        "suggested_test": "t", "current": True, "status": "open",
    }
    first = merge([row], {})
    first["findings"][0]["status"] = "confirmed"
    second = merge([row], first)
    assert second["findings"][0]["status"] == "confirmed"
    assert second["findings"][0]["occurrences"] == 2


def test_research_contours_do_not_turn_collection_into_profit_verdict(tmp_path: Path):
    xsec = tmp_path / "runtime" / "xsec_v3_shadow" / "ledger.jsonl"
    xsec.parent.mkdir(parents=True)
    xsec.write_text(
        "\n".join([
            json.dumps({"previous_phase_markout": {"gross_return": -0.02}}),
            json.dumps({"previous_phase_markout": {"gross_return": 0.005}}),
        ]),
        encoding="utf-8",
    )
    funding = tmp_path / "runtime" / "funding_positioning_post_n42_frozen_summary.json"
    funding.write_text(json.dumps({
        "closed": 0,
        "status_counts": {"pending_fill": 2},
        "universe_sha256": "a" * 64,
    }), encoding="utf-8")
    alpaca = tmp_path / "runtime" / "alpaca_adaptive_v1_shadow_latest.json"
    alpaca.write_text(json.dumps({"mode": "shadow_no_orders", "orders_sent": False}), encoding="utf-8")

    rows, coverage = collect_research_contours(tmp_path)
    assert coverage["fresh"] is True
    assert {row["strategy"] for row in rows} == {"xsec_v3", "funding_positioning", "alpaca_adaptive_v1"}
    assert all(row["safe_for_profit_verdict"] is False for row in rows)
