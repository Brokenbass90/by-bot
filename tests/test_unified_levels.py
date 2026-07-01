"""Tests for bot.unified_levels — one call, all level types, typed + nearest."""
from bot.unified_levels import unified_levels, LevelSet, Level


def _rows():
    rows, seg = [], [100, 100.5, 99.5, 100.3, 100.8, 99.6, 100.4, 101.0, 100.2, 99.7]
    for k in range(8):
        for j, p in enumerate(seg):
            rows.append([k * 10 + j, p, p + 0.3, p - 0.3, p, 1000 + j * 50])
    return rows


def test_insufficient_data():
    ls = unified_levels([[i, 1, 1, 1, 1, 1] for i in range(5)])
    assert isinstance(ls, LevelSet) and ls.ok is False


def test_aggregates_multiple_kinds():
    ls = unified_levels(_rows())
    assert ls.ok is True and len(ls.levels) > 0
    kinds = {l.kind for l in ls.levels}
    # at least sloped + hvn + liquidity present
    assert {"sloped", "hvn", "liquidity"} <= kinds


def test_round_levels_only_when_requested():
    off = unified_levels(_rows(), include_round=False)
    on = unified_levels(_rows(), include_round=True)
    assert not any(l.kind == "round" for l in off.levels)
    assert any(l.kind == "round" for l in on.levels)


def test_nearest_support_and_resistance_typed():
    ls = unified_levels(_rows())
    if ls.nearest_support:
        assert isinstance(ls.nearest_support, Level)
        assert ls.nearest_support.price <= ls.price and ls.nearest_support.side == "support"
    if ls.nearest_resistance:
        assert ls.nearest_resistance.price >= ls.price and ls.nearest_resistance.side == "resistance"


def test_by_kind_filter():
    ls = unified_levels(_rows())
    assert ls.by_kind("hvn") == [l for l in ls.levels if l.kind == "hvn"]


def test_every_level_has_side_and_dist():
    ls = unified_levels(_rows())
    for l in ls.levels:
        assert l.side in ("support", "resistance")
        assert l.dist_atr >= 0
