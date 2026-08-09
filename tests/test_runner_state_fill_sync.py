from trade_state import TradeState

from bot.runner_state import (
    apply_runner_state,
    reconcile_runner_qty_with_exchange,
    sync_runner_qty_after_fill,
)


class _RunnerSignal:
    tps = [0.95, 0.90]
    tp_fracs = [0.55, 0.45]
    trailing_atr_mult = 1.5
    trailing_atr_period = 14
    trail_activate_rr = 1.0
    be_trigger_rr = 1.0
    be_lock_rr = 0.02
    time_stop_bars = 2016


def test_runner_qty_syncs_to_actual_fill_before_partials() -> None:
    tr = TradeState(symbol="ADAUSDT", side="Sell")
    tr.sl_price = 0.1936

    assert apply_runner_state(tr, _RunnerSignal(), 97.0, use_runner=True) is True
    assert tr.initial_qty == 97.0
    assert tr.remaining_qty == 97.0

    assert sync_runner_qty_after_fill(tr, 191.0) is True
    assert tr.initial_qty == 191.0
    assert tr.remaining_qty == 191.0


def test_runner_qty_sync_does_not_rebase_after_partial_hit() -> None:
    tr = TradeState(symbol="ADAUSDT", side="Sell")
    tr.sl_price = 0.1936

    assert apply_runner_state(tr, _RunnerSignal(), 191.0, use_runner=True) is True
    tr.tp_hit[0] = True
    tr.remaining_qty = 86.0

    assert sync_runner_qty_after_fill(tr, 191.0) is False
    assert tr.initial_qty == 191.0
    assert tr.remaining_qty == 86.0


def test_reconcile_open_runner_uses_increased_broker_size() -> None:
    tr = TradeState(symbol="ADAUSDT", side="Sell")
    tr.runner_enabled = True
    tr.initial_qty = 180.0
    tr.remaining_qty = 180.0

    assert reconcile_runner_qty_with_exchange(tr, 270.0) is True
    assert tr.initial_qty == 270.0
    assert tr.remaining_qty == 270.0


def test_reconcile_open_runner_preserves_initial_size_after_partial_close() -> None:
    tr = TradeState(symbol="ADAUSDT", side="Sell")
    tr.runner_enabled = True
    tr.initial_qty = 180.0
    tr.remaining_qty = 180.0
    tr.tp_hit = [True, False]

    assert reconcile_runner_qty_with_exchange(tr, 81.0) is True
    assert tr.initial_qty == 180.0
    assert tr.remaining_qty == 81.0
