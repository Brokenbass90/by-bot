from trade_state import TradeState


def test_sync_prunes_already_closed_trade_without_exchange_call(monkeypatch):
    import smart_pump_reversal_bot as bot

    class FailClient:
        def get_position_summary(self, _symbol):
            raise AssertionError("closed trades must not query the exchange again")

    trade = TradeState(symbol="DASHUSDT", side="Buy", strategy="range")
    trade.status = "CLOSED"
    trades = {("Bybit", "DASHUSDT"): trade}

    monkeypatch.setattr(bot, "DRY_RUN", False)
    monkeypatch.setattr(bot, "TRADE_CLIENT", FailClient())
    monkeypatch.setattr(bot, "TRADES", trades)

    bot.sync_trades_with_exchange()

    assert trades == {}
