from scripts.run_forex_multi_strategy_gate import (
    _default_pip_size,
    _default_spread,
    _default_swap,
)


def test_xau_contract_does_not_reuse_fx_decimal_pip_or_costs():
    assert _default_pip_size("XAUUSD") == 0.01
    assert _default_spread("XAUUSD") == 35.0
    assert _default_swap("XAUUSD") == -20.0


def test_major_fx_contracts_remain_unchanged():
    assert _default_pip_size("EURUSD") == 0.0001
    assert _default_spread("EURUSD") == 1.0
    assert _default_swap("EURUSD") == -0.3
    assert _default_pip_size("USDJPY") == 0.01
