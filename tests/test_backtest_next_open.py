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
