from bot.deepseek_overlay import _snapshot_truth_gate


def test_snapshot_truth_gate_requires_explicit_fresh_authority() -> None:
    ok, blockers = _snapshot_truth_gate({"ai_full_context": {}})

    assert ok is False
    assert blockers == ["critical_live_truth_missing_or_unverified"]


def test_snapshot_truth_gate_accepts_reviewed_live_truth() -> None:
    authority = {
        "complete": True,
        "unclassified_sleeves": [],
        "live_money_sleeves": ["att1"],
        "components": {
            "att1": {
                "enabled": True,
                "risk_mult": 0.1,
                "execution_authority": "money",
            }
        },
    }
    ok, blockers = _snapshot_truth_gate(
        {
            "runtime_authority": authority,
            "ai_full_context": {
                "heartbeat": {"strategy_runtime_config": {"authority": authority}},
                "critical_truth_assessment": {
                    "control_recommendations_allowed": True,
                    "blockers": [],
                    "live_money_sleeves_by_heartbeat": ["att1"],
                }
            }
        }
    )

    assert ok is True
    assert blockers == []


def test_snapshot_truth_gate_rejects_same_sleeve_risk_contract_race() -> None:
    current = {
        "complete": True,
        "unclassified_sleeves": [],
        "live_money_sleeves": ["att1"],
        "components": {
            "att1": {"enabled": True, "risk_mult": 0.7, "execution_authority": "money"}
        },
    }
    cached = {
        **current,
        "components": {
            "att1": {"enabled": True, "risk_mult": 0.1, "execution_authority": "money"}
        },
    }

    ok, blockers = _snapshot_truth_gate(
        {
            "runtime_authority": current,
            "ai_full_context": {
                "heartbeat": {"strategy_runtime_config": {"authority": cached}},
                "critical_truth_assessment": {
                    "control_recommendations_allowed": True,
                    "blockers": [],
                    "live_money_sleeves_by_heartbeat": ["att1"],
                },
            },
        }
    )

    assert ok is False
    assert "runtime_ai_context_authority_contract_mismatch" in blockers
