from scripts import build_ai_full_context as builder


def test_position_truth_does_not_mislabel_runner_export_as_broker_truth() -> None:
    result = builder.position_truth_assessment(
        heartbeat={"open_trades": 2},
        positions={"source_kind": "runner_local_export", "count": 2, "positions": []},
    )

    assert result["counts_match"] is True
    assert result["broker_confirmed"] is False
    assert result["status"] == "NOT_CONFIRMED"
    assert "broker_position_truth_not_confirmed" in result["blockers"]


def test_position_truth_accepts_explicit_direct_broker_snapshot() -> None:
    result = builder.position_truth_assessment(
        heartbeat={"open_trades": 1},
        positions={
            "source_kind": "broker_direct_readonly",
            "broker_state": "CONFIRMED",
            "count": 1,
            "positions": [{"symbol": "BTCUSDT"}],
        },
    )

    assert result["status"] == "CONFIRMED"
    assert result["blockers"] == []


def test_critical_truth_allows_only_fresh_matching_live_state():
    heartbeat = {
        "strategy_runtime_config": {
            "enabled": {"att1": True, "ivb1": True},
            "risk_mult": {"att1": 0.1, "ivb1": 0.0},
            "authority": {
                "complete": True,
                "unclassified_sleeves": [],
                "live_money_sleeves": ["att1"],
                "components": {
                    "att1": {"enabled": True, "execution_authority": "money"},
                    "ivb1": {"enabled": True, "execution_authority": "none_or_shadow"},
                },
            },
            "operator_live_override": {"enabled": True, "loaded": True},
        }
    }
    freshness = {
        "heartbeat": {"present": True, "age_sec": 10},
        "live_positions": {"present": True, "age_sec": 12},
        "allocator_state": {"present": True, "age_sec": 15},
        "regime": {"present": True, "age_sec": 20},
        "operator_snapshot": {"present": True, "age_sec": 25},
    }
    canonical = {"live": {"crypto_money_sleeves": ["att1"], "att1_risk_mult": 0.1}}

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )

    assert result["control_recommendations_allowed"] is True
    assert result["live_money_sleeves_by_heartbeat"] == ["att1"]


def test_critical_truth_uses_hourly_allocator_freshness_contract():
    heartbeat = {
        "strategy_runtime_config": {
            "risk_mult": {"att1": 0.1},
            "authority": {
                "complete": True,
                "unclassified_sleeves": [],
                "live_money_sleeves": ["att1"],
                "components": {
                    "att1": {"enabled": True, "execution_authority": "money"},
                },
            },
        }
    }
    canonical = {"live": {"crypto_money_sleeves": ["att1"], "att1_risk_mult": 0.1}}
    freshness = {
        "heartbeat": {"present": True, "age_sec": 10},
        "live_positions": {"present": True, "age_sec": 10},
        "allocator_state": {"present": True, "age_sec": 10_799},
        "regime": {"present": True, "age_sec": 10},
        "operator_snapshot": {"present": True, "age_sec": 10},
    }

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )
    assert result["control_recommendations_allowed"] is True

    freshness["allocator_state"]["age_sec"] = 10_801
    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )
    assert result["control_recommendations_allowed"] is False
    assert "allocator_state_missing_or_stale" in result["blockers"]


def test_critical_truth_fails_closed_on_stale_or_conflicting_sources():
    heartbeat = {
        "strategy_runtime_config": {
            "enabled": {"att1": True, "range": True},
            "risk_mult": {"att1": 0.7, "range": 0.25},
            "authority": {
                "complete": True,
                "unclassified_sleeves": [],
                "live_money_sleeves": ["att1", "range"],
                "components": {
                    "att1": {"enabled": True, "execution_authority": "money"},
                    "range": {"enabled": True, "execution_authority": "money"},
                },
            },
            "operator_live_override": {"enabled": True, "loaded": False},
        }
    }
    freshness = {
        "heartbeat": {"present": True, "age_sec": 500},
        "live_positions": {"present": False, "age_sec": None},
        "allocator_state": {"present": False, "age_sec": None},
        "regime": {"present": True, "age_sec": 8_000},
        "operator_snapshot": {"present": True, "age_sec": 8_000},
    }
    canonical = {"live": {"crypto_money_sleeves": ["att1"], "att1_risk_mult": 0.1}}

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )

    assert result["control_recommendations_allowed"] is False
    assert any("heartbeat_missing_or_stale" in x for x in result["blockers"])
    assert any("money_sleeve_conflict" in x for x in result["blockers"])
    assert any("att1_risk_conflict" in x for x in result["blockers"])


def test_critical_truth_rejects_incomplete_runtime_authority():
    heartbeat = {
        "strategy_runtime_config": {
            "risk_mult": {"att1": 0.1},
            "authority": {
                "complete": False,
                "unclassified_sleeves": ["pump_fade"],
                "live_money_sleeves": ["att1"],
                "components": {
                    "att1": {"enabled": True, "execution_authority": "money"},
                },
            },
        }
    }
    freshness = {
        "heartbeat": {"present": True, "age_sec": 10},
        "live_positions": {"present": True, "age_sec": 10},
        "allocator_state": {"present": True, "age_sec": 10},
        "regime": {"present": True, "age_sec": 10},
        "operator_snapshot": {"present": True, "age_sec": 10},
    }
    canonical = {"live": {"crypto_money_sleeves": ["att1"], "att1_risk_mult": 0.1}}

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat, freshness=freshness, canonical_state=canonical
    )

    assert result["control_recommendations_allowed"] is False
    assert "runtime_authority_missing_or_incomplete" in result["blockers"]


def test_critical_truth_treats_empty_canonical_money_list_as_strict_zero() -> None:
    heartbeat = {
        "strategy_runtime_config": {
            "risk_mult": {"att1": 0.1},
            "authority": {
                "complete": True,
                "unclassified_sleeves": [],
                "live_money_sleeves": ["att1"],
                "components": {
                    "att1": {"enabled": True, "execution_authority": "money"},
                },
            },
        }
    }
    freshness = {
        "heartbeat": {"present": True, "age_sec": 10},
        "live_positions": {"present": True, "age_sec": 10},
        "allocator_state": {"present": True, "age_sec": 10},
        "regime": {"present": True, "age_sec": 10},
        "operator_snapshot": {"present": True, "age_sec": 10},
    }

    result = builder.critical_truth_assessment(
        heartbeat=heartbeat,
        freshness=freshness,
        canonical_state={"live": {"crypto_money_sleeves": []}},
    )

    assert result["control_recommendations_allowed"] is False
    assert any("money_sleeve_conflict" in row for row in result["blockers"])
