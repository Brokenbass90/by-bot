import pandas as pd

from scripts.run_fx_d1_carry_trend_v1 import _metrics, _one_way_cost_bps


def test_metrics_reports_red_months_and_drawdown():
    idx = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-02-02"], utc=True)
    row = _metrics(pd.Series([0.10, -0.20, 0.05], index=idx))
    assert row["calendar_months"] == 2
    assert row["negative_months"] == 1
    assert row["max_drawdown_pct"] == 20.0


def test_cost_contract_converts_spread_to_one_way_bps():
    costs = {
        "instruments": {"EURUSD": {"spread_pips_base": 1.0}},
        "research_arms": {"base": {"spread_mult": 1.0, "commission_bps_per_side": 0.0}},
    }
    assert round(_one_way_cost_bps("EURUSD", 1.0, costs, "base"), 6) == 0.5
