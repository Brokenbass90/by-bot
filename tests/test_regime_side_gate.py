from bot.regime_side_gate import regime_side_allowed


def test_bull_regime_allows_longs_and_blocks_shorts():
    assert regime_side_allowed("Buy", "BULL_TREND") is True
    assert regime_side_allowed("long", "bull_chop") is True
    assert regime_side_allowed("Sell", "bull_chop") is False


def test_bear_regime_allows_shorts_and_blocks_longs():
    assert regime_side_allowed("Sell", "BEAR_TREND") is True
    assert regime_side_allowed("short", "bear_chop") is True
    assert regime_side_allowed("Buy", "bear_chop") is False


def test_neutral_and_unknown_preserve_strategy_side_config():
    assert regime_side_allowed("Buy", "NEUTRAL") is True
    assert regime_side_allowed("Sell", "unknown") is True


def test_disabled_gate_bypasses_regime_but_not_invalid_side_when_enabled():
    assert regime_side_allowed("Sell", "BULL_TREND", enabled=False) is True
    assert regime_side_allowed("", "BULL_TREND") is False
