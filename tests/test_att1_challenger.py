from bot.att1_challenger import classify_descending_rsi_50_70


def test_att1_descending_rsi_challenger_accepts_frozen_rule():
    result = classify_descending_rsi_50_70(
        "short",
        "att1_short_trendline tl=10 slope=-1.250%/d rsi=55.0 "
        "r2=0.900 pivots=3",
    )

    assert result.accepted
    assert result.reason == "accepted"
    assert result.slope_pct_day == -1.25
    assert result.rsi == 55.0


def test_att1_descending_rsi_challenger_is_behavior_neutral_rejection_label():
    result = classify_descending_rsi_50_70(
        "short",
        "att1_short_trendline tl=10 slope=-1.250%/d rsi=48.0",
    )

    assert not result.accepted
    assert result.reason == "rsi_outside_50_70"


def test_att1_descending_rsi_challenger_fails_closed_on_missing_features():
    result = classify_descending_rsi_50_70("short", "legacy reason")

    assert not result.accepted
    assert result.reason == "missing_entry_features"
