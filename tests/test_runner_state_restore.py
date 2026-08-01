from trade_state import TradeState

from bot.runner_state import (
    apply_runner_snapshot,
    plan_runner_target_close,
    runner_snapshot_from_trade,
)


def test_runner_snapshot_roundtrip_restores_ladder_and_trailing():
    tr = TradeState(symbol="ADAUSDT", side="Sell", strategy="att1_trendline_touch")
    tr.runner_enabled = True
    tr.initial_qty = 138.0
    tr.remaining_qty = 138.0
    tr.tps = [0.1836, 0.1777]
    tr.tp_fracs = [0.55, 0.45]
    tr.tp_hit = [False, False]
    tr.initial_sl_price = 0.1936
    tr.be_trigger_rr = 1.0
    tr.be_lock_rr = 0.1
    tr.trail_mult = 1.7
    tr.trail_period = 14
    tr.trail_activate_rr = 1.5
    tr.trail_armed = True
    tr.ll = 0.1788
    tr.time_stop_sec = 604800

    snap = runner_snapshot_from_trade(tr)
    restored = TradeState(symbol="ADAUSDT", side="Sell", strategy="att1_trendline_touch")

    assert apply_runner_snapshot(restored, snap, exchange_qty=138.0) is True
    assert restored.runner_enabled is True
    assert restored.tps == [0.1836, 0.1777]
    assert restored.tp_fracs == [0.55, 0.45]
    assert restored.tp_hit == [False, False]
    assert restored.trail_mult == 1.7
    assert restored.trail_armed is True
    assert restored.ll == 0.1788
    assert restored.time_stop_sec == 604800


def test_runner_snapshot_infers_hit_target_from_reduced_exchange_qty():
    snap = {
        "runner_enabled": True,
        "initial_qty": 100.0,
        "remaining_qty": 100.0,
        "tps": [90.0, 80.0],
        "tp_fracs": [0.55, 0.45],
        "tp_hit": [False, False],
        "initial_sl_price": 105.0,
    }
    restored = TradeState(symbol="TESTUSDT", side="Sell", strategy="runner")

    assert apply_runner_snapshot(restored, snap, exchange_qty=45.0) is True
    assert restored.remaining_qty == 45.0
    assert restored.tp_hit == [True, False]


def test_runner_close_plan_uses_actual_step_aligned_quantity_and_final_flush():
    first_close, first_remaining = plan_runner_target_close(
        initial_qty=1.2,
        remaining_qty=1.2,
        target_frac=0.55,
        qty_step=0.1,
        final_target=False,
    )
    assert first_close == 0.6
    assert first_remaining == 0.6

    final_close, final_remaining = plan_runner_target_close(
        initial_qty=1.2,
        remaining_qty=first_remaining,
        target_frac=0.45,
        qty_step=0.1,
        final_target=True,
    )
    assert final_close == 0.6
    assert final_remaining == 0.0


def test_runner_close_plan_does_not_mark_sub_step_intermediate_slice_as_closed():
    close_qty, remaining = plan_runner_target_close(
        initial_qty=0.15,
        remaining_qty=0.15,
        target_frac=0.1,
        qty_step=0.1,
        final_target=False,
    )
    assert close_qty == 0.0
    assert remaining == 0.15


def test_runner_close_plan_preserves_intentional_residual_runner():
    close_qty, remaining = plan_runner_target_close(
        initial_qty=1.2,
        remaining_qty=0.8,
        target_frac=0.25,
        qty_step=0.1,
        final_target=False,
    )
    assert close_qty == 0.3
    assert remaining == 0.5
