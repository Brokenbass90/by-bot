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
