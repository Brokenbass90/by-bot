from __future__ import annotations

import pytest

from backtest.alpaca_bakeoff_wf import _max_drawdown_pct, _summarize_adaptive


def test_drawdown_includes_initial_capital_before_first_endpoint() -> None:
    assert _max_drawdown_pct([950.0, 980.0], initial_value=1000.0) == pytest.approx(5.0)


def test_adaptive_summary_does_not_hide_initial_loss() -> None:
    summary = _summarize_adaptive(
        initial_capital=1000.0,
        equity_curve=[920.0, 940.0, 930.0],
        monthly_returns=[-0.08, 0.02, -0.01],
        trade_returns=[-0.08, 0.02, -0.01],
    )

    assert summary["max_dd_pct"] == pytest.approx(8.0)
