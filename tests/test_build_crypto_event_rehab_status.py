from __future__ import annotations

from scripts.build_crypto_event_rehab_status import build_status


def test_pair_status_keeps_sides_and_risk_separate() -> None:
    pump = {
        "verdict": "NO_PROMOTION",
        "failed_gates": ["min_trades", "holdout_min_trades"],
        "metrics": {
            "base": {
                "trades": 39,
                "profit_factor": 1.4,
                "return_pct": 2.1,
                "max_drawdown_pct": 2.7,
            },
            "stress": {
                "trades": 39,
                "profit_factor": 1.23,
                "return_pct": 1.2,
                "max_drawdown_pct": 3.0,
            },
            "holdout_stress": {"trades": 6, "profit_factor": 6.3, "net_r": 1.0},
            "traded_symbols": 13,
            "positive_symbols": 8,
        },
    }
    event = {
        "status": "BLOCKED_RESEARCH_RUNNER_DATA",
        "performance_permission": "PERFORMANCE_FORBIDDEN",
        "live_permission": "LIVE_FORBIDDEN",
        "identity": {"integrity_pass": True},
        "blockers": [{"code": "RUNNER_ABSENT"}],
    }

    status = build_status(
        pump=pump,
        event_preflight=event,
        latest_state={"sequence": 100, "as_of_ms": 1_785_000_000_000},
        launch_receipt={"deadline_at_ms": 1_785_100_000_000},
        label_receipts=[],
    )

    assert status["research_only"] is True
    assert status["executable"] is False
    assert status["portfolio_role"]["initial_risk"] == 0
    assert status["portfolio_role"]["statistics_must_remain_side_separated"] is True
    assert status["lanes"][0]["side"] == "short_only"
    assert status["lanes"][1]["side"] == "long_only"
    assert status["prospective_discovery"]["postrun_label_gate_complete"] is False
