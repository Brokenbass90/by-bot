def _client():
    class Client:
        name = "main"

    return Client()


def test_restore_exchange_position_recovers_strategy_and_broker_protection(monkeypatch):
    import smart_pump_reversal_bot as bot

    trades = {}
    monkeypatch.setattr(bot, "TRADES", trades)
    monkeypatch.setattr(bot, "TRADE_CLIENT", _client())
    monkeypatch.setattr(
        bot,
        "_get_last_open_entry_event",
        lambda *_args, **_kwargs: {
            "strategy": "range",
            "entry_ts": 12345,
            "entry_price": 100.0,
            "tp_price": 105.0,
            "sl_price": 98.0,
        },
    )
    monkeypatch.setattr(bot, "tg_trade", lambda *_args, **_kwargs: None)

    restored = bot._restore_trade_state_from_exchange_row(
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.01",
            "avgPrice": "101",
            "takeProfit": "105",
            "stopLoss": "98",
        },
        source="startup",
    )

    trade = trades[("Bybit", "BTCUSDT")]
    assert restored is True
    assert trade.strategy == "range"
    assert trade.status == "OPEN"
    assert trade.avg == 101.0
    assert trade.tp_price == 105.0
    assert trade.sl_price == 98.0
    assert trade.tpsl_on_exchange is True


def test_restore_unknown_position_marks_missing_broker_protection(monkeypatch):
    import smart_pump_reversal_bot as bot

    trades = {}
    events = []
    monkeypatch.setattr(bot, "TRADES", trades)
    monkeypatch.setattr(bot, "TRADE_CLIENT", _client())
    monkeypatch.setattr(bot, "_get_last_open_entry_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "tg_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bot,
        "_append_live_trade_event",
        lambda event, symbol, trade, **extra: events.append((event, symbol, trade, extra)),
    )

    restored = bot._restore_trade_state_from_exchange_row(
        {
            "symbol": "ETHUSDT",
            "side": "Sell",
            "size": "0.1",
            "avgPrice": "2500",
            "takeProfit": "0",
            "stopLoss": "2550",
        },
        source="startup",
    )

    trade = trades[("Bybit", "ETHUSDT")]
    assert restored is True
    assert trade.strategy == "bootstrap"
    assert trade.status == "OPEN"
    assert trade.tp_price is None
    assert trade.sl_price == 2550.0
    assert trade.tpsl_on_exchange is False
    assert events[0][0:2] == ("bootstrap_adopted", "ETHUSDT")
    assert events[0][3]["missing_protection"] == ["tp"]
