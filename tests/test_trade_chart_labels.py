from bot.trade_chart_labels import normalize_bybit_timeframe, signal_timeframe_label


def test_recorded_signal_timeframe_wins() -> None:
    assert signal_timeframe_label(
        "att1_trendline_touch",
        {"signal_timeframe": "240"},
        att1_default="60",
    ) == ("240m", "recorded_signal_reason")


def test_old_att1_snapshot_uses_labeled_config_fallback() -> None:
    assert signal_timeframe_label(
        "att1_trendline_touch",
        {},
        att1_default="60",
    ) == ("60m", "att1_config_fallback")


def test_unknown_strategy_does_not_invent_timeframe() -> None:
    assert signal_timeframe_label("mystery", {}, att1_default="60") == (
        "unknown",
        "not_recorded",
    )


def test_named_bybit_intervals_are_normalized() -> None:
    assert normalize_bybit_timeframe("D") == "1d"
    assert normalize_bybit_timeframe("W") == "1w"
    assert normalize_bybit_timeframe("M") == "1M"
