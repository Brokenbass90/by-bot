from bot.tpsl_policy import preserve_existing_tpsl, restored_position_manual_lock


def test_bootstrap_with_only_sl_is_not_manual_locked():
    assert not restored_position_manual_lock(
        "bootstrap",
        tp_present=False,
        sl_present=True,
    )


def test_bootstrap_with_full_protection_is_manual_locked():
    assert restored_position_manual_lock(
        "bootstrap",
        tp_present=True,
        sl_present=True,
    )


def test_tracked_position_preserves_existing_manual_side():
    assert restored_position_manual_lock(
        "alt_inplay_breakdown_v1",
        tp_present=False,
        sl_present=True,
    )


def test_missing_tp_is_filled_without_overwriting_existing_sl():
    tp, sl = preserve_existing_tpsl(None, 105.0, 95.0, 110.0)
    assert tp == 95.0
    assert sl == 105.0


# --- P0-fix regression: strategy-designed TP/SL must survive the fill ---
from bot.tpsl_policy import should_preserve_strategy_tpsl

_LEGACY = {"pump", "pump_fade"}


def test_modern_strategy_keeps_its_own_stop():
    # the bug: breakdown/att1/ivb1 etc. used to get a 0.3% stop slapped on.
    for strat in (
        "alt_inplay_breakdown_v1", "att1_trendline_touch", "flat_resistance_fade",
        "impulse_volume_breakout_v1", "hzbo1_zone_break", "elder_triple_screen_v2",
        "alt_bear_regime_continuation_v1",
    ):
        assert should_preserve_strategy_tpsl(strat, has_strategy_levels=True, legacy_pct_strategies=_LEGACY) is True


def test_legacy_pump_uses_pct_fallback():
    assert should_preserve_strategy_tpsl("pump", has_strategy_levels=True, legacy_pct_strategies=_LEGACY) is False
    assert should_preserve_strategy_tpsl("pump_fade", has_strategy_levels=True, legacy_pct_strategies=_LEGACY) is False


def test_missing_levels_falls_back_to_pct():
    assert should_preserve_strategy_tpsl("alt_inplay_breakdown_v1", has_strategy_levels=False, legacy_pct_strategies=_LEGACY) is False


def test_none_strategy_defaults_to_legacy_pct():
    assert should_preserve_strategy_tpsl(None, has_strategy_levels=True, legacy_pct_strategies=_LEGACY) is False
