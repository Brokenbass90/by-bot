from __future__ import annotations

import pytest

from backtest.engine import _calc_qty
from bot.risk_sizing_contract import calculate_notional_from_stop_pct, calculate_risk_size
from strategies.signals import TradeSignal


def _signal(*, entry: float = 100.0, stop: float = 98.0) -> TradeSignal:
    return TradeSignal(
        symbol="TESTUSDT",
        side="long",
        entry=entry,
        sl=stop,
        tp=104.0,
        strategy="parity_test",
        reason="sizing parity",
    )


def test_uncapped_size_hits_fixed_risk_target() -> None:
    decision = calculate_risk_size(
        equity=1000.0,
        entry=100.0,
        stop=98.0,
        side="long",
        target_risk_fraction=0.01,
        max_notional_usd=1000.0,
    )
    assert decision.accepted
    assert decision.qty == pytest.approx(5.0)
    assert decision.effective_risk_usd == pytest.approx(10.0)
    assert decision.binding_constraint == "risk_target"


def test_cap_exposes_effective_risk_instead_of_claiming_target_risk() -> None:
    decision = calculate_risk_size(
        equity=1000.0,
        entry=100.0,
        stop=98.0,
        side="long",
        target_risk_fraction=0.01,
        max_notional_usd=250.0,
        min_fill_fraction=0.40,
    )
    assert decision.accepted
    assert decision.fill_fraction == pytest.approx(0.5)
    assert decision.effective_risk_usd == pytest.approx(5.0)
    assert decision.binding_constraint == "notional_cap"


def test_heavily_capped_trade_is_rejected() -> None:
    decision = calculate_risk_size(
        equity=1000.0,
        entry=100.0,
        stop=98.0,
        side="long",
        target_risk_fraction=0.01,
        max_notional_usd=150.0,
        min_fill_fraction=0.40,
    )
    assert not decision.accepted
    assert decision.reason == "below_min_fill_fraction"
    assert decision.fill_fraction == pytest.approx(0.30)


def test_backtest_uses_the_shared_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIN_NOTIONAL_FILL_FRAC", "0.40")
    sig = _signal()
    expected = calculate_risk_size(
        equity=1000.0,
        entry=sig.entry,
        stop=sig.sl,
        side=sig.side,
        target_risk_fraction=0.01,
        max_notional_usd=250.0,
        min_fill_fraction=0.40,
    )
    assert _calc_qty(1000.0, sig, 0.01, 250.0) == pytest.approx(expected.qty)


def test_wrong_side_stop_is_rejected() -> None:
    decision = calculate_risk_size(
        equity=1000.0,
        entry=100.0,
        stop=102.0,
        side="long",
        target_risk_fraction=0.01,
        max_notional_usd=1000.0,
    )
    assert not decision.accepted
    assert decision.reason == "nonpositive_stop_distance"


@pytest.mark.parametrize(
    ("equity", "entry", "stop", "risk_fraction", "risk_mult", "vol_mult", "cap"),
    [
        (1021.07, 0.8136, 0.8205, 0.01, 0.10, 0.44, 970.0),
        (1000.0, 100.0, 98.0, 0.01, 1.00, 1.00, 1000.0),
        (1000.0, 100.0, 98.0, 0.01, 1.00, 1.00, 250.0),
    ],
)
def test_live_stop_pct_and_backtest_fixed_r_have_pre_round_parity(
    equity, entry, stop, risk_fraction, risk_mult, vol_mult, cap
) -> None:
    stop_pct = abs(entry - stop) / entry * 100.0
    live = calculate_notional_from_stop_pct(
        equity=equity,
        stop_pct=stop_pct,
        target_risk_fraction=risk_fraction,
        risk_multiplier=risk_mult,
        volatility_multiplier=vol_mult,
        max_notional_usd=cap,
        min_fill_fraction=0.40,
    )
    backtest = calculate_risk_size(
        equity=equity,
        entry=entry,
        stop=stop,
        target_risk_fraction=risk_fraction * risk_mult * vol_mult,
        max_notional_usd=cap,
        min_fill_fraction=0.40,
    )

    assert live.accepted == backtest.accepted
    assert live.effective_notional_usd == pytest.approx(
        backtest.effective_notional_usd, rel=1e-12
    )
    assert live.effective_risk_usd == pytest.approx(
        backtest.effective_risk_usd, rel=1e-12
    )


def test_live_stop_pct_contract_rejects_same_heavy_cap_as_backtest() -> None:
    decision = calculate_notional_from_stop_pct(
        equity=1000.0,
        stop_pct=2.0,
        target_risk_fraction=0.01,
        risk_multiplier=1.0,
        volatility_multiplier=1.0,
        max_notional_usd=150.0,
        min_fill_fraction=0.40,
    )

    assert not decision.accepted
    assert decision.reason == "below_min_fill_fraction"
