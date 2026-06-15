from trade_state import TradeState

from bot.live_position_view import build_live_position_row


def test_runner_position_keeps_exchange_tp_none_but_exposes_targets():
    tr = TradeState(symbol="LTCUSDT", side="Sell", strategy="flat_resistance_fade")
    tr.avg = 43.90
    tr.qty = 0.7
    tr.sl_price = 44.13
    tr.tp_price = None
    tr.runner_enabled = True
    tr.initial_qty = 0.7
    tr.remaining_qty = 0.7
    tr.tps = [43.55, 43.10]
    tr.tp_fracs = [0.6, 0.4]
    tr.tp_hit = [False, False]
    tr.time_stop_sec = 172800

    row = build_live_position_row(exchange="Bybit", symbol="LTCUSDT", tr=tr, current=43.80)

    assert row["tp"] is None
    assert row["exchange_tp"] is None
    assert row["tp_model"] == "runner_ladder"
    assert row["sl"] == 44.13
    assert row["runner"]["enabled"] is True
    assert row["runner"]["targets"][0] == {
        "index": 1,
        "price": 43.55,
        "frac": 0.6,
        "hit": False,
        "status": "pending",
    }
    assert row["runner"]["trailing"]["enabled"] is False
    assert row["runner"]["time_stop_enabled"] is True


def test_exchange_tp_position_uses_exchange_model():
    tr = TradeState(symbol="BTCUSDT", side="Buy", strategy="single_tp_probe")
    tr.avg = 100.0
    tr.qty = 1.0
    tr.sl_price = 95.0
    tr.tp_price = 110.0

    row = build_live_position_row(exchange="Bybit", symbol="BTCUSDT", tr=tr, current=102.0)

    assert row["tp_model"] == "exchange_tp"
    assert row["tp"] == 110.0
    assert row["exchange_tp"] == 110.0
    assert row["runner"]["enabled"] is False
