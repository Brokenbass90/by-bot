"""Tests for bot.position_sizing — fixed-R, vol-aware, budget-capped sizing."""
from bot.position_sizing import plan_size, SizePlan


def test_no_equity():
    assert plan_size(0, 100, 99).place is False


def test_zero_risk_distance_skips():
    p = plan_size(1000, 100, 100)
    assert p.place is False and p.reason == "nonpositive_risk_distance"


def test_basic_one_percent_risk():
    p = plan_size(1000, 100, 99, risk_pct=1.0)
    assert p.place is True
    assert abs(p.risk_amount - 10.0) < 1e-9
    assert abs(p.risk_pct_effective - 1.0) < 1e-9
    assert abs(p.qty - 10.0) < 1e-9


def test_fixed_R_invariant_across_stop_distance():
    # THE point: risk amount is identical regardless of stop width; only qty changes
    tight = plan_size(1000, 100, 99, risk_pct=1.0)
    wide = plan_size(1000, 100, 96, risk_pct=1.0)
    assert abs(tight.risk_amount - wide.risk_amount) < 1e-9
    assert wide.qty < tight.qty


def test_portfolio_budget_caps_risk():
    p = plan_size(1000, 100, 99, risk_pct=1.0, open_risk_pct=1.3, max_open_risk_pct=1.5)
    assert p.place is True
    assert abs(p.risk_pct_effective - 0.20) < 1e-6      # only 0.2% budget remained
    assert p.capped is True


def test_portfolio_budget_full_skips():
    p = plan_size(1000, 100, 99, risk_pct=1.0, open_risk_pct=1.5, max_open_risk_pct=1.5)
    assert p.place is False and p.reason == "portfolio_risk_budget_full"


def test_leverage_cap_limits_notional():
    p = plan_size(1000, 100, 99.9, risk_pct=1.0, max_position_pct=100.0)
    assert p.leverage <= 1.0 + 1e-9
    assert p.capped is True
    assert p.risk_pct_effective < 1.0        # capped notional -> lower effective risk


def test_vol_target_scales_risk_down_in_high_vol():
    quiet = plan_size(1000, 100, 99, risk_pct=1.0)
    volatile = plan_size(1000, 100, 99, risk_pct=1.0, atr_pct=4.0, target_atr_pct=2.0)
    assert volatile.vol_scalar < 1.0
    assert volatile.risk_amount < quiet.risk_amount


def test_below_min_notional_skips():
    p = plan_size(100, 100, 99, risk_pct=0.01, min_notional=10.0)
    assert p.place is False and p.reason.startswith("below_min_notional")
