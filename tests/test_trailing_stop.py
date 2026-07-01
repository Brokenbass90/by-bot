"""Tests for bot.trailing_stop — breakeven + Chandelier trail (let winners run)."""
from bot.trailing_stop import new_trail, update_trail, simulate_trail, PositionTrail


def test_new_trail_risk():
    pt = new_trail("long", 100, 99)
    assert isinstance(pt, PositionTrail) and pt.risk == 1.0 and pt.stop == 99


def test_breakeven_moves_stop_to_entry():
    pt = new_trail("long", 100, 99)
    out = update_trail(pt, high=101, low=100.5, atr=1.0, be_trigger_rr=1.0)
    assert out["moved_be"] is True and pt.stop > 100.0


def test_trail_activates_and_tightens_one_way():
    pt = new_trail("long", 100, 99)
    update_trail(pt, 101, 100.5, atr=1.0)            # BE
    update_trail(pt, 105, 104, atr=1.0)              # trail -> 105-2.5 = 102.5
    assert pt.trail_on is True and abs(pt.stop - 102.5) < 1e-6
    before = pt.stop
    update_trail(pt, 103, 102.6, atr=1.0)            # lower bar must NOT loosen stop
    assert pt.stop >= before


def test_exit_uses_pre_raise_stop_no_same_bar_whipsaw():
    # a bar that reaches 1R (sets BE) must NOT retroactively stop out on its own low
    pt = new_trail("long", 100, 99)
    out = update_trail(pt, high=101, low=100.0, atr=1.0, be_trigger_rr=1.0)
    assert out["exit"] is False


def test_simulate_runner_captures_big_R():
    rows = [[i, 100 + i * 0.5, 100 + i * 0.5 + 0.5, 100 + i * 0.5 - 0.3, 100 + i * 0.5 + 0.2, 1000]
            for i in range(20)]
    rows += [[20, 110, 110, 104, 104.5, 1000]]       # sharp pullback triggers trail exit
    res = simulate_trail(rows, "long", 100, 99, atr=1.0, start_idx=1)
    assert res["trailed"] is True and res["r_multiple"] > 3.0


def test_simulate_immediate_reversal_is_minus_1R():
    rows = [[1, 100, 100.2, 98.5, 99, 1000]]
    res = simulate_trail(rows, "long", 100, 99, atr=1.0, start_idx=0)
    assert abs(res["r_multiple"] + 1.0) < 1e-6


def test_short_side_trails():
    pt = new_trail("short", 100, 101)                # risk 1, stop above
    update_trail(pt, 99, 98.5, atr=1.0)              # 1R favorable -> BE
    update_trail(pt, 96, 95, atr=1.0)               # trail -> 95 + 2.5 = 97.5
    assert pt.trail_on is True and abs(pt.stop - 97.5) < 1e-6
