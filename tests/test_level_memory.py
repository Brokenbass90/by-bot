"""Level memory — synthetic reaction histories must classify correctly."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.level_memory import level_respect, symbol_respect

H = 3_600_000
LEVEL = 100.0


def _bar(i, o, h, l, c):
    return [i * H, o, h, l, c, 10.0]


def _drift(start_i, n, px, rng=1.0):
    """Quiet bars far from the level to keep ATR sane and separate touches."""
    return [_bar(start_i + k, px, px + rng, px - rng, px) for k in range(n)]


def _bounce_touch(start_i):
    """Approach 100 from above, touch, reject upward strongly."""
    return [
        _bar(start_i, 104, 104.5, 103, 103.5),
        _bar(start_i + 1, 103.5, 103.8, 100.1, 100.4),   # touch (within tol)
        _bar(start_i + 2, 100.4, 102.5, 100.2, 102.3),   # move away >= 1 ATR
        _bar(start_i + 3, 102.3, 103.5, 102, 103.2),
    ]


def _sweep_touch(start_i):
    """Pierce below 100, reclaim, leave upward (закол)."""
    return [
        _bar(start_i, 103, 103.5, 102, 102.5),
        _bar(start_i + 1, 102.5, 102.6, 99.6, 100.3),    # pierce 0.4 then close back above
        _bar(start_i + 2, 100.3, 102.8, 100.2, 102.6),   # reclaim + away
        _bar(start_i + 3, 102.6, 103.2, 102.1, 103.0),
    ]


def _break_touch(start_i):
    """Slice through 100 and keep falling."""
    return [
        _bar(start_i, 103, 103.5, 102, 102.4),
        _bar(start_i + 1, 102.4, 102.5, 98.0, 98.2),     # deep close below
        _bar(start_i + 2, 98.2, 98.5, 96.5, 96.8),
        _bar(start_i + 3, 96.8, 97.2, 95.9, 96.1),
    ]


def _shallow_sustained_break_touch(start_i):
    """Close only modestly beyond support, then hold below it."""
    rows = [
        _bar(start_i, 103, 103.4, 102.0, 102.5),
        _bar(start_i + 1, 102.5, 102.6, 99.2, 99.5),
    ]
    rows += [
        _bar(start_i + k, 99.5, 99.7, 99.1, 99.4)
        for k in range(2, 9)
    ]
    return rows


def _resistance_bounce_touch(start_i):
    """Approach 100 from below, touch resistance, reject downward."""
    return [
        _bar(start_i, 97.0, 98.0, 96.5, 97.5),
        _bar(start_i + 1, 97.5, 99.9, 97.3, 99.5),
        _bar(start_i + 2, 99.5, 99.7, 97.0, 97.2),
        _bar(start_i + 3, 97.2, 97.5, 96.0, 96.3),
    ]


def _series(touch_builders):
    rows = _drift(0, 40, 105.0)
    i = 40
    for build in touch_builders:
        rows += build(i)
        i += 4
        rows += _drift(i, 10, 105.0)
        i += 10
    rows += _drift(i, 10, 105.0)
    return rows


def test_respectful_symbol_scores_high():
    rows = _series([_bounce_touch, _bounce_touch, _bounce_touch, _bounce_touch])
    st = level_respect(rows, LEVEL)
    assert st.touches >= 4
    assert st.breaks == 0
    assert st.respect_score >= 0.9


def test_breaking_symbol_scores_low():
    rows = _series([_break_touch, _break_touch, _break_touch])
    st = level_respect(rows, LEVEL)
    assert st.breaks >= 2
    assert st.bounces == 0
    assert st.respect_score <= 0.4


def test_shallow_sustained_close_beyond_level_is_break_not_bounce():
    rows = _drift(0, 40, 105.0)
    i = 40
    for _ in range(3):
        event = _shallow_sustained_break_touch(i)
        rows += event
        i += len(event)
        rows += _drift(i, 10, 105.0)
        i += 10
    rows += _drift(i, 10, 105.0)
    st = level_respect(rows, LEVEL, approach="from_above")
    assert st.breaks >= 2
    assert st.bounces == 0
    assert st.respect_score <= 0.4


def test_sweeps_count_half():
    rows = _series([_sweep_touch, _sweep_touch, _break_touch, _break_touch])
    st = level_respect(rows, LEVEL)
    assert st.sweeps >= 1 and st.breaks >= 1
    assert 0.1 <= st.respect_score <= 0.7


def test_no_touches_gives_nan_and_short_history_safe():
    rows = _drift(0, 60, 120.0)               # never near 100
    st = level_respect(rows, LEVEL)
    assert st.touches == 0
    assert st.respect_score != st.respect_score  # NaN
    tiny = level_respect(_drift(0, 5, 100.0), LEVEL)
    assert tiny.touches == 0


def test_symbol_respect_excludes_tiny_n_levels():
    rows = _series([_bounce_touch, _bounce_touch, _bounce_touch, _bounce_touch])
    out = symbol_respect(rows, [LEVEL, 500.0], min_touches_per_level=3)
    # 500 never touched -> not rated; 100 rated high
    assert out["rated_levels"] == 1
    assert out["symbol_respect"] >= 0.9
    assert any(not d["rated"] for d in out["per_level"])


def test_approach_filter_separates_support_and_resistance_reactions():
    rows = _series([
        _bounce_touch,
        _resistance_bounce_touch,
        _bounce_touch,
        _resistance_bounce_touch,
    ])
    both = level_respect(rows, LEVEL)
    support = level_respect(rows, LEVEL, approach="from_above")
    resistance = level_respect(rows, LEVEL, approach="from_below")

    assert both.approach == "both"
    assert support.approach == "from_above"
    assert resistance.approach == "from_below"
    assert support.touches >= 2
    assert resistance.touches >= 2
    assert set(support.touch_indices).isdisjoint(resistance.touch_indices)
    assert set(support.touch_indices) | set(resistance.touch_indices) <= set(both.touch_indices)


def test_invalid_approach_fails_closed():
    with pytest.raises(ValueError, match="approach"):
        level_respect(_drift(0, 60, 105.0), LEVEL, approach="sideways")
