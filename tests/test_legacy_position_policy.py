from bot.legacy_position_policy import should_apply_legacy_pump_fade_dca


def test_legacy_dca_is_limited_to_pump_fade_family() -> None:
    assert should_apply_legacy_pump_fade_dca("pump")
    assert should_apply_legacy_pump_fade_dca("pump_fade")


def test_att1_and_other_strategies_cannot_inherit_pump_fade_dca() -> None:
    for strategy in (
        "att1_trendline_touch",
        "bounce",
        "range",
        "alt_inplay_breakdown_v1",
        "ivb1",
        "",
        None,
    ):
        assert not should_apply_legacy_pump_fade_dca(strategy)
