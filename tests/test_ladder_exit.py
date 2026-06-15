"""Deterministic tests for the runner-ladder exit simulator."""

from backtest.ladder_exit import simulate_ladder_exit

# long setup: entry 100, sl 90 -> risk = 10; tps 110 (1R), 120 (2R); fracs .6/.4
LONG = dict(is_long=True, entry=100.0, sl=90.0, tps=[110.0, 120.0], fracs=[0.6, 0.4])


def test_full_ladder_tp1_then_tp2():
    # bar1 reaches 110, bar2 reaches 120
    bars = [(110.0, 105.0), (120.0, 112.0)]
    R, rem = simulate_ladder_exit(bars=bars, **LONG)
    # 0.6*1R + 0.4*2R = 1.4R
    assert abs(R - 1.4) < 1e-9
    assert rem == 0.0


def test_tp1_then_breakeven_stop():
    # bar1 hits 110 (TP1 -> stop moves to entry 100), bar2 dips to 100 (breakeven)
    bars = [(110.0, 104.0), (108.0, 100.0)]
    R, rem = simulate_ladder_exit(bars=bars, **LONG)
    # 0.6*1R + 0.4*0R(breakeven) = 0.6R
    assert abs(R - 0.6) < 1e-9
    assert rem == 0.0


def test_stop_before_any_tp_is_minus_1R():
    bars = [(105.0, 90.0)]  # low touches initial SL 90
    R, rem = simulate_ladder_exit(bars=bars, **LONG)
    assert abs(R - (-1.0)) < 1e-9
    assert rem == 0.0


def test_fees_reduce_R():
    bars = [(110.0, 105.0), (120.0, 112.0)]
    R0, _ = simulate_ladder_exit(bars=bars, fee_bps_round_trip=0.0, **LONG)
    Rf, _ = simulate_ladder_exit(bars=bars, fee_bps_round_trip=20.0, **LONG)
    assert Rf < R0          # fees always cost something
    # stop_frac = 10/100 = 0.1; fee_units = 1(entry)+0.6+0.4 = 2.0
    # fee_R = 2.0 * 0.002 / 0.1 = 0.04
    assert abs((R0 - Rf) - 0.04) < 1e-9


def test_short_side_symmetry():
    # short: entry 100, sl 110 -> risk 10; tps 90(1R),80(2R)
    bars = [(95.0, 90.0), (88.0, 80.0)]
    R, rem = simulate_ladder_exit(is_long=False, entry=100.0, sl=110.0,
                                  tps=[90.0, 80.0], fracs=[0.6, 0.4], bars=bars)
    assert abs(R - 1.4) < 1e-9
    assert rem == 0.0


def test_open_remainder_when_unresolved():
    # only TP1 hit, no further bars -> 0.4 remains open
    bars = [(110.0, 105.0)]
    R, rem = simulate_ladder_exit(bars=bars, **LONG)
    assert abs(R - 0.6) < 1e-9   # booked TP1 portion
    assert abs(rem - 0.4) < 1e-9
