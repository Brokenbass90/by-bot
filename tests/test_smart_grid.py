"""Tests for bot.smart_grid — regime-aware grid with break kill-switch."""
import random
from bot.smart_grid import grid_plan, GridState


def _jagged_range(n=140, seed=3, band=2.5):
    random.seed(seed); rows = []; prev = 100.0
    for i in range(n):
        c = 100 + 0.2 * (prev - 100) + random.uniform(-band, band)
        o = prev
        h = max(o, c) + abs(random.uniform(0, 0.8))
        l = min(o, c) - abs(random.uniform(0, 0.8))
        rows.append([i, o, h, l, c, 1500]); prev = c
    return rows


def _trend(n=140, slope=0.5):
    return [[i, 100 + i * slope, 100 + i * slope + 0.3, 100 + i * slope - 0.3,
             100 + i * slope + 0.1, 1000] for i in range(n)]


def test_insufficient_data():
    g = grid_plan([[i, 1, 1, 1, 1, 1] for i in range(10)])
    assert isinstance(g, GridState) and g.active is False


def test_range_activates_grid():
    g = grid_plan(_jagged_range(), min_width_atr=1.0, require_flat_regime=False)
    assert g.active is True and g.action == "run"
    total = g.buy_levels + g.sell_levels
    assert len(total) >= 1
    for lv in total:
        assert g.lower <= lv <= g.upper                # grid inside channel
    for b in g.buy_levels:
        assert b < g.extra["price"]                    # buys below price
    for s in g.sell_levels:
        assert s > g.extra["price"]                    # sells above price


def test_trend_does_not_grid():
    g = grid_plan(_trend(), require_flat_regime=True)
    assert g.active is False and g.action in ("idle",)


def test_breakout_halts_and_flattens():
    rows = _jagged_range() + [[200, 102, 112, 102, 111, 4000]]   # blow through channel top
    g = grid_plan(rows, min_width_atr=1.0, require_flat_regime=False)
    assert g.action == "halt_and_flatten" and g.active is False
    assert g.reason in ("channel_break", "regime_high_vol")


def test_narrow_channel_idle():
    # force a very high min_width so any channel is "too narrow"
    g = grid_plan(_jagged_range(), min_width_atr=99.0, require_flat_regime=False)
    assert g.active is False and ("narrow" in g.reason or g.reason == "no_channel")
