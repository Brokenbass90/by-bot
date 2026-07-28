from bot.strategy_regime_gate import strategy_regime_gate_decision


def test_breakdown_style_gate_allows_only_fresh_allowed_regime():
    decision = strategy_regime_gate_decision(
        "bear_trend",
        overlay_fresh=True,
        allowed_regimes={"BEAR_TREND"},
    )
    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_gate_blocks_bull_and_neutral_regimes():
    for regime in ("bull_trend", "bull_chop", "neutral", ""):
        decision = strategy_regime_gate_decision(
            regime,
            overlay_fresh=True,
            allowed_regimes={"BEAR_TREND"},
        )
        assert decision.allowed is False


def test_gate_fails_closed_when_overlay_is_stale():
    decision = strategy_regime_gate_decision(
        "bear_trend",
        overlay_fresh=False,
        allowed_regimes={"BEAR_TREND"},
        fail_closed=True,
    )
    assert decision.allowed is False
    assert decision.reason == "overlay_stale_or_missing"


def test_gate_can_be_explicitly_disabled_for_research_replay():
    decision = strategy_regime_gate_decision(
        "bull_trend",
        overlay_fresh=False,
        allowed_regimes={"BEAR_TREND"},
        enabled=False,
    )
    assert decision.allowed is True
    assert decision.reason == "gate_disabled"
