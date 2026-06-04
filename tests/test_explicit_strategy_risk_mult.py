from backtest.run_portfolio import _explicit_strategy_risk_mult


def test_ivb1_explicit_risk_mult_does_not_require_allocator(monkeypatch) -> None:
    monkeypatch.setenv("IVB1_RISK_MULT", "0.25")
    monkeypatch.delenv("ALLOCATOR_ENABLE", raising=False)

    assert _explicit_strategy_risk_mult("impulse_volume_breakout_v1") == 0.25


def test_missing_explicit_risk_mult_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("IVB1_RISK_MULT", raising=False)
    monkeypatch.delenv("IMPULSE_RISK_MULT", raising=False)

    assert _explicit_strategy_risk_mult("impulse_volume_breakout_v1") is None


def test_explicit_zero_risk_mult_remains_disabled(monkeypatch) -> None:
    monkeypatch.setenv("IVB1_RISK_MULT", "0")

    assert _explicit_strategy_risk_mult("impulse_volume_breakout_v1") == 0.0
