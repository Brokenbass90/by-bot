"""Tests for bot.level_entry — maker-limit-at-level entry planner."""
from bot.level_entry import plan_level_entry, simulate_fill, LimitEntryPlan


def _base(n=29):
    return [[i, 100, 100.4, 99.6, 100, 1000] for i in range(n)]


def test_bad_input():
    p = plan_level_entry([[0, 1, 1, 1, 1, 1]], 1.0, "support")
    assert isinstance(p, LimitEntryPlan) and p.place is False


def test_long_plan_at_support_is_maker_with_tight_stop():
    rows = _base() + [[29, 99.9, 100.0, 99.6, 99.7, 1000]]
    p = plan_level_entry(rows, level=99.5, side="support")
    assert p.place is True and p.side == "long" and p.order_type == "limit"
    assert p.stop < p.limit_price < p.tp2         # long ordering
    assert abs(p.rr2 - 2.5) < 1e-6                # asymmetric take honored
    assert p.risk > 0 and p.stop_pct > 0


def test_short_plan_at_resistance():
    rows = _base() + [[29, 100.1, 100.4, 100.0, 100.3, 1000]]
    p = plan_level_entry(rows, level=100.5, side="resistance")
    assert p.place is True and p.side == "short"
    assert p.tp2 < p.limit_price < p.stop
    assert abs(p.rr2 - 2.5) < 1e-6


def test_chase_guard_skips_late_entry():
    rows = _base() + [[29, 100.0, 100.2, 99.8, 100.0, 1000]]
    p = plan_level_entry(rows, level=98.0, side="support")   # price already far above
    assert p.place is False and p.reason == "would_chase_above_level"


def test_stop_too_wide_rejected():
    rows = _base() + [[29, 99.9, 100.0, 99.6, 99.7, 1000]]
    p = plan_level_entry(rows, level=99.5, side="support", max_stop_pct=0.001)
    assert p.place is False and p.reason.startswith("stop_too_wide")


def test_maker_gives_tighter_stop_than_close_entry():
    rows = _base() + [[29, 99.9, 100.0, 99.6, 99.7, 1000]]
    p = plan_level_entry(rows, level=99.5, side="support")
    close_entry_risk = 99.7 - p.stop        # entering at bar close instead of the level
    assert close_entry_risk > p.risk        # maker-at-level stop is tighter -> higher R


def test_simulate_fill_dip_fills_and_runaway_expires():
    rows = _base() + [[29, 99.9, 100.0, 99.6, 99.7, 1000]]
    p = plan_level_entry(rows, level=99.5, side="support")
    filled = simulate_fill([[30, 99.7, 99.8, 99.4, 99.6, 1000]], p)
    assert filled["filled"] is True and filled["fill_bar"] == 0
    away = simulate_fill([[30, 100.1, 100.6, 100.0, 100.5, 1000]] * 4, p)
    assert away["filled"] is False and away["reason"] == "expired_unfilled"


def test_no_order_not_filled():
    skip = plan_level_entry(_base() + [[29, 100, 100.2, 99.8, 100, 1000]], 98.0, "support")
    res = simulate_fill([[30, 97, 98.1, 96, 97, 1]], skip)
    assert res["filled"] is False and res["reason"] == "no_order"
