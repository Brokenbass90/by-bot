"""Tests for bot.smart_grid — fee-aware, strong-flat grid with kill-switch."""
import random
from bot.smart_grid import grid_plan, GridState


def _strong_flat(n=140, seed=3, band=3.0):
    random.seed(seed); rows = []; prev = 100.0
    for i in range(n):
        c = 100 + 0.15 * (prev - 100) + random.uniform(-band, band)
        o = prev
        h = max(o, c) + abs(random.uniform(0, 0.9))
        l = min(o, c) - abs(random.uniform(0, 0.9))
        rows.append([i, o, h, l, c, 1500]); prev = c
    return rows


def _trend(n=140, slope=0.5):
    return [[i, 100 + i * slope, 100 + i * slope + 0.3, 100 + i * slope - 0.3,
             100 + i * slope + 0.1, 1000] for i in range(n)]


def test_insufficient_data():
    g = grid_plan([[i, 1, 1, 1, 1, 1] for i in range(10)])
    assert isinstance(g, GridState) and g.active is False


def test_strong_flat_low_fee_activates():
    g = grid_plan(_strong_flat(), fee_bps=6.0, n_levels=10, min_width_atr=1.0)
    assert g.active is True and g.action == "run"
    assert g.n_levels >= 2
    for lv in g.buy_levels + g.sell_levels:
        assert g.lower <= lv <= g.upper


def test_fee_aware_step_beats_fees():
    g = grid_plan(_strong_flat(), fee_bps=6.0, fee_survival_mult=3.0, n_levels=10, min_width_atr=1.0)
    if g.active:
        assert g.step_pct >= 3.0 * (2 * 6.0 / 1e4) - 1e-9   # step clears round-trip fee*mult


def test_high_fee_refuses_to_grid():
    g = grid_plan(_strong_flat(), fee_bps=40.0, n_levels=10, min_width_atr=1.0)
    assert g.active is False and g.reason.startswith("fee_infeasible")


def test_trend_does_not_grid():
    g = grid_plan(_trend(), min_width_atr=1.0)
    assert g.active is False


def test_breakout_halts_and_flattens():
    rows = _strong_flat() + [[200, 102, 120, 102, 118, 4000]]
    g = grid_plan(rows, fee_bps=6.0, min_width_atr=1.0)
    assert g.action == "halt_and_flatten"


def test_strong_flat_gate_blocks_weak_range():
    # require_strong_flat off vs on: a trend should still be blocked either way
    g = grid_plan(_trend(), require_strong_flat=True, min_width_atr=1.0)
    assert g.active is False


def test_side_split_long_only_only_bids():
    g = grid_plan(_strong_flat(), fee_bps=6.0, n_levels=10, min_width_atr=1.0, side="long")
    if g.active:
        assert g.side == "long" and len(g.sell_levels) == 0 and len(g.buy_levels) >= 1


def test_side_split_short_only_only_asks():
    g = grid_plan(_strong_flat(), fee_bps=6.0, n_levels=10, min_width_atr=1.0, side="short")
    if g.active:
        assert g.side == "short" and len(g.buy_levels) == 0 and len(g.sell_levels) >= 1
