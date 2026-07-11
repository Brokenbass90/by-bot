from scripts import build_ai_full_context as builder


def test_critical_truth_allows_only_fresh_matching_live_state():
    heartbeat = {
        "strategy_runtime_config": {
            "enabled": {"att1": True, "ivb1": True},
            "risk_mult": {"att1": 0.1, "ivb1": 0.0},
            "operator_live_override": {"enabled": True, "loaded": True},
        }
    }
    freshness = {
        "heartbeat": {"present": True, "age_sec": 10},
        "live_positions": {"present": True, "age_sec": 12},
    }
    canonical = {"live": {"crypto_money_sleeves": ["att1"], "att1_risk_mult": 0.1}}

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )

    assert result["control_recommendations_allowed"] is True
    assert result["live_money_sleeves_by_heartbeat"] == ["att1"]


def test_critical_truth_fails_closed_on_stale_or_conflicting_sources():
    heartbeat = {
        "strategy_runtime_config": {
            "enabled": {"att1": True, "range": True},
            "risk_mult": {"att1": 0.7, "range": 0.25},
            "operator_live_override": {"enabled": True, "loaded": False},
        }
    }
    freshness = {
        "heartbeat": {"present": True, "age_sec": 500},
        "live_positions": {"present": False, "age_sec": None},
    }
    canonical = {"live": {"crypto_money_sleeves": ["att1"], "att1_risk_mult": 0.1}}

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )

    assert result["control_recommendations_allowed"] is False
    assert any("heartbeat_missing_or_stale" in x for x in result["blockers"])
    assert any("money_sleeve_conflict" in x for x in result["blockers"])
    assert any("att1_risk_conflict" in x for x in result["blockers"])
