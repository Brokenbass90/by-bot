from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from backtest.alpaca_bakeoff_wf import _profit_factor, run_adaptive_monthly
from strategies.alpaca_adaptive_v1 import AdaptiveConfig


def _frame(closes: list[float]):
    dates = pd.date_range("2021-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [x * 1.01 for x in closes],
            "Low": [x * 0.99 for x in closes],
            "Close": closes,
        },
        index=dates,
    )


def test_profit_factor_handles_losses_and_no_losses() -> None:
    assert _profit_factor([0.10, -0.05, 0.05]) == pytest.approx(3.0)
    assert _profit_factor([0.10, 0.05]) == float("inf")
    assert _profit_factor([]) == 0.0


def test_adaptive_gate_moves_to_cash_when_index_is_below_sma() -> None:
    cfg = AdaptiveConfig(
        mom_fast=2,
        mom_slow=5,
        vol_period=5,
        trend_sma=3,
        regime_index_sma=10,
        max_positions=2,
    )
    data = {
        "SPY": _frame([100 - i for i in range(80)]),
        "AAA": _frame([50 + i * 0.5 for i in range(80)]),
    }

    result = run_adaptive_monthly(
        data,
        start="2021-02-01",
        end="2021-04-15",
        initial_capital=1000.0,
        max_positions=2,
        fee_bps_round_trip=10.0,
        use_gate=True,
        cfg=cfg,
        rebalance_every=5,
    )

    assert result["stats"]["trades"] == 0
    assert result["stats"]["return_pct"] == pytest.approx(0.0)


def test_adaptive_ungated_can_trade_qualified_names() -> None:
    cfg = AdaptiveConfig(
        mom_fast=2,
        mom_slow=5,
        vol_period=5,
        trend_sma=3,
        regime_index_sma=10,
        max_positions=2,
    )
    data = {
        "SPY": _frame([100 - i for i in range(80)]),
        "AAA": _frame([50 + i * 0.5 for i in range(80)]),
        "BBB": _frame([40 + i * 0.2 for i in range(80)]),
    }

    result = run_adaptive_monthly(
        data,
        start="2021-02-01",
        end="2021-04-15",
        initial_capital=1000.0,
        max_positions=2,
        fee_bps_round_trip=10.0,
        use_gate=False,
        cfg=cfg,
        rebalance_every=5,
    )

    assert result["stats"]["trades"] > 0
