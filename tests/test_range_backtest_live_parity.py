from archive.strategies_retired.range_wrapper import RangeBacktestStrategy


def _unused_fetch(*_args, **_kwargs):
    return []


def test_range_backtest_adapter_honors_live_side_and_stop_env(monkeypatch):
    monkeypatch.setenv("RANGE_ALLOW_LONG", "0")
    monkeypatch.setenv("RANGE_ALLOW_SHORT", "1")
    monkeypatch.setenv("RANGE_SL_WIDTH_FRAC", "0.11")
    monkeypatch.setenv("RANGE_SL_ATR_MULT", "0.88")
    monkeypatch.setenv("RANGE_CONFIRM_LIMIT", "40")

    strategy = RangeBacktestStrategy(_unused_fetch)

    assert strategy.strategy.allow_long is False
    assert strategy.strategy.allow_short is True
    assert strategy.strategy.sl_width_frac == 0.11
    assert strategy.strategy.sl_atr_mult == 0.88
    assert strategy.strategy.confirm_limit == 40
