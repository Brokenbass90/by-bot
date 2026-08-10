from backtest.engine import BacktestParams, Candle, KlineStore, run_symbol_backtest
from backtest.portfolio_engine import run_portfolio_backtest
from strategies.signals import TradeSignal


def _store() -> KlineStore:
    candles = [
        Candle(ts=0, o=99.0, h=101.0, l=98.0, c=100.0, v=1.0),
        Candle(ts=300_000, o=105.0, h=111.0, l=104.0, c=109.0, v=1.0),
        Candle(ts=600_000, o=109.0, h=109.0, l=108.0, c=108.0, v=1.0),
    ]
    return KlineStore("BTCUSDT", candles)


def _one_shot_selector():
    emitted = False

    def selector(symbol, store, ts_ms, last_price):
        nonlocal emitted
        if emitted:
            return None
        emitted = True
        return TradeSignal(
            strategy="demo",
            symbol=symbol,
            side="long",
            entry=100.0,
            sl=90.0,
            tp=110.0,
            reason="test",
        )

    return selector


def test_portfolio_next_open_fills_on_following_bar_and_processes_its_range():
    store = _store()
    result = run_portfolio_backtest(
        {"BTCUSDT": store},
        _one_shot_selector(),
        params=BacktestParams(
            starting_equity=100.0,
            risk_pct=0.01,
            cap_notional_usd=1_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=True,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_ts == 300_000
    assert trade.entry_price == 105.0
    assert trade.exit_ts == 300_000
    assert trade.exit_price == 110.0
    assert trade.signal_ts == 300_000
    assert trade.signal_entry_price == 100.0
    assert trade.initial_sl == 90.0
    assert trade.tp_prices == "110"
    assert trade.signal_reason == "test"
    assert trade.initial_notional > 0.0
    assert trade.initial_risk_usd > 0.0


def test_portfolio_legacy_mode_keeps_signal_price_and_timestamp():
    store = _store()
    result = run_portfolio_backtest(
        {"BTCUSDT": store},
        _one_shot_selector(),
        params=BacktestParams(
            starting_equity=100.0,
            risk_pct=0.01,
            cap_notional_usd=1_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=False,
        ),
    )

    assert len(result.trades) == 1
    assert result.trades[0].entry_ts == 0
    assert result.trades[0].entry_price == 100.0


def test_invalid_signal_is_not_opened():
    def selector(symbol, store, ts_ms, last_price):
        return TradeSignal(
            strategy="invalid",
            symbol=symbol,
            side="long",
            entry=100.0,
            sl=110.0,
            tp=90.0,
        )

    result = run_portfolio_backtest(
        {"BTCUSDT": _store()},
        selector,
        params=BacktestParams(fee_bps=0.0, slippage_bps=0.0),
    )

    assert result.trades == []


def test_portfolio_selector_receives_execution_bar_close_timestamp():
    seen = []

    def selector(symbol, store, ts_ms, last_price):
        seen.append(ts_ms)
        return None

    run_portfolio_backtest(
        {"BTCUSDT": _store()},
        selector,
        params=BacktestParams(fee_bps=0.0, slippage_bps=0.0),
    )

    assert seen[:3] == [300_000, 600_000, 900_000]


def test_single_symbol_engine_uses_next_open_too():
    emitted = False

    def signal_fn(store, bar):
        nonlocal emitted
        if emitted:
            return None
        emitted = True
        return TradeSignal("demo", store.symbol, "long", 100.0, 90.0, 110.0)

    trades, _curve = run_symbol_backtest(
        _store(),
        strategy_name="demo",
        signal_fn=signal_fn,
        params=BacktestParams(
            starting_equity=100.0,
            risk_pct=0.01,
            cap_notional_usd=1_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=True,
        ),
    )

    assert len(trades) == 1
    assert trades[0].entry_ts == 300_000
    assert trades[0].entry_price == 105.0
    assert trades[0].exit_ts == 300_000


def test_portfolio_limit_signal_waits_for_touch_then_fills_at_limit():
    candles = [
        Candle(ts=0, o=105.0, h=106.0, l=104.0, c=105.0, v=1.0),
        Candle(ts=300_000, o=105.0, h=106.0, l=101.0, c=102.0, v=1.0),  # no fill yet
        Candle(ts=600_000, o=102.0, h=111.0, l=99.0, c=110.0, v=1.0),   # touches limit, then TP
    ]
    store = KlineStore("BTCUSDT", candles)
    emitted = False

    def selector(symbol, store, ts_ms, last_price):
        nonlocal emitted
        if emitted:
            return None
        emitted = True
        sig = TradeSignal("limit_demo", symbol, "long", 100.0, 95.0, 110.0)
        sig.entry_order_type = "limit"
        sig.limit_validity_bars = 2
        return sig

    result = run_portfolio_backtest(
        {"BTCUSDT": store},
        selector,
        params=BacktestParams(
            starting_equity=100.0,
            risk_pct=0.01,
            cap_notional_usd=1_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=True,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_ts == 600_000
    assert trade.entry_price == 100.0
    assert trade.exit_price == 110.0


def test_portfolio_limit_signal_expires_unfilled():
    candles = [
        Candle(ts=0, o=105.0, h=106.0, l=104.0, c=105.0, v=1.0),
        Candle(ts=300_000, o=105.0, h=106.0, l=101.0, c=102.0, v=1.0),
        Candle(ts=600_000, o=102.0, h=103.0, l=101.0, c=102.0, v=1.0),
        Candle(ts=900_000, o=102.0, h=103.0, l=101.0, c=102.0, v=1.0),
    ]
    store = KlineStore("BTCUSDT", candles)
    emitted = False

    def selector(symbol, store, ts_ms, last_price):
        nonlocal emitted
        if emitted:
            return None
        emitted = True
        sig = TradeSignal("limit_demo", symbol, "long", 100.0, 95.0, 110.0)
        sig.entry_order_type = "limit"
        sig.limit_validity_bars = 2
        return sig

    result = run_portfolio_backtest(
        {"BTCUSDT": store},
        selector,
        params=BacktestParams(
            starting_equity=100.0,
            risk_pct=0.01,
            cap_notional_usd=1_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=True,
        ),
    )

    assert result.trades == []


def test_portfolio_maker_requires_trade_through_and_preserves_signal_price(monkeypatch):
    monkeypatch.setenv("BACKTEST_MAKER_THROUGH_BPS", "2")
    candles = [
        Candle(ts=0, o=101.0, h=102.0, l=100.5, c=101.0, v=1.0),
        # Bare touch at 100 is not enough for a maker fill.
        Candle(ts=300_000, o=101.0, h=101.5, l=100.0, c=100.5, v=1.0),
        # A 2 bps trade-through fills the resting order at 100.
        Candle(ts=600_000, o=100.5, h=101.0, l=99.9, c=100.2, v=1.0),
        Candle(ts=900_000, o=100.2, h=103.0, l=100.0, c=102.0, v=1.0),
    ]
    emitted = False

    def selector(symbol, store, ts_ms, last_price):
        nonlocal emitted
        if emitted:
            return None
        emitted = True
        sig = TradeSignal("maker_demo", symbol, "long", 100.0, 95.0, 102.0)
        sig.entry_order_type = "limit"
        sig.limit_validity_bars = 3
        sig.maker_entry = True
        sig.maker_signal_entry = 101.0
        return sig

    result = run_portfolio_backtest(
        {"BTCUSDT": KlineStore("BTCUSDT", candles)},
        selector,
        params=BacktestParams(
            starting_equity=100.0,
            risk_pct=0.01,
            cap_notional_usd=1_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=True,
        ),
    )

    assert len(result.trades) == 1
    assert result.trades[0].entry_ts == 600_000
    assert result.trades[0].entry_price == 100.0
    assert result.trades[0].signal_entry_price == 101.0
    assert result.execution_stats["maker_orders_placed"] == 1
    assert result.execution_stats["maker_orders_filled"] == 1
    assert result.execution_stats["maker_fill_rate"] == 1.0


def test_portfolio_does_not_replace_resting_maker_and_records_nonfill(monkeypatch):
    monkeypatch.setenv("BACKTEST_MAKER_THROUGH_BPS", "2")
    candles = [
        Candle(ts=i * 300_000, o=101.0, h=101.5, l=100.4, c=101.4, v=1.0)
        for i in range(5)
    ]
    calls = 0

    def selector(symbol, store, ts_ms, last_price):
        nonlocal calls
        calls += 1
        sig = TradeSignal("maker_demo", symbol, "long", 100.0, 95.0, 110.0)
        sig.entry_order_type = "limit"
        sig.limit_validity_bars = 2
        sig.maker_entry = True
        sig.maker_signal_entry = 101.0
        return sig

    result = run_portfolio_backtest(
        {"BTCUSDT": KlineStore("BTCUSDT", candles)},
        selector,
        params=BacktestParams(
            starting_equity=100.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            entry_on_next_open=True,
        ),
    )

    assert result.trades == []
    # One lifecycle is held until expiry; a fresh signal can only be created
    # after it expires, rather than overwriting it on every bar.
    assert calls == 2
    assert result.execution_stats["maker_orders_placed"] == 2
    assert result.execution_stats["maker_orders_filled"] == 0
    assert result.execution_stats["maker_orders_expired"] == 1
    assert result.execution_stats["maker_orders_pending_eop"] == 1
    assert result.execution_stats["maker_fill_rate_resolved"] == 0.0
    assert result.execution_stats["maker_expiry_markout_n"] == 1
