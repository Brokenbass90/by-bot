"""Tests for bot.retest_quality — shared level-freshness + retest scorer."""
from bot.retest_quality import score_retest, best_retest, RetestScore


def _baseline(n=30, px=100.0, vol=1000.0):
    return [[i, px, px + 0.4, px - 0.4, px, vol] for i in range(n)]


def test_bad_input():
    st = score_retest([[0, 1, 1, 1, 1, 1]], 1.0, "support")
    assert st.ok is False and st.entry_ok is False


def test_support_retest_is_long_only():
    rows = _baseline()
    rows.append([30, 99.9, 100.0, 99.4, 99.7, 2000])     # lower wick + volume at support
    st = score_retest(rows, level=99.5, side="support", last_touch_idx=28, touches=3)
    assert st.entry_ok is True
    assert st.long_ok is True and st.short_ok is False
    assert st.side == "long"
    assert 0.0 <= st.quality <= 1.0


def test_resistance_retest_is_short_only():
    rows = _baseline()
    rows.append([30, 100.1, 100.6, 100.0, 100.3, 2000])  # upper wick + volume at resistance
    st = score_retest(rows, level=100.5, side="resistance", last_touch_idx=28, touches=3)
    assert st.entry_ok is True
    assert st.short_ok is True and st.long_ok is False
    assert st.side == "short"


def test_stale_level_rejected():
    rows = _baseline()
    rows.append([30, 99.9, 100.0, 99.4, 99.7, 2000])
    st = score_retest(rows, level=99.5, side="support", last_touch_idx=0,
                      touches=3, max_age_bars=10)
    assert st.entry_ok is False and st.reason == "level_stale"


def test_far_from_level_rejected():
    rows = _baseline(n=31)
    st = score_retest(rows, level=95.0, side="support", last_touch_idx=29, touches=3)
    assert st.entry_ok is False and st.reason == "too_far_from_level"


def test_rejection_wick_raises_quality():
    base = _baseline()
    strong = base + [[30, 99.9, 100.0, 99.4, 99.7, 2000]]   # big lower wick
    weak = base + [[30, 99.9, 100.0, 99.65, 99.7, 2000]]     # tiny wick
    qs = score_retest(strong, 99.5, "support", last_touch_idx=28, touches=3).quality
    qw = score_retest(weak, 99.5, "support", last_touch_idx=28, touches=3).quality
    assert qs > qw


def test_side_mutually_exclusive():
    rows = _baseline()
    rows.append([30, 99.9, 100.0, 99.4, 99.7, 2000])
    st = score_retest(rows, level=99.5, side="support", last_touch_idx=28, touches=3)
    assert not (st.long_ok and st.short_ok)


def test_best_retest_finds_fresh_support():
    rows, ts = [], 0
    seg = [100.0, 100.1, 99.5, 100.1, 100.0, 100.2, 99.5, 100.1, 100.0, 100.2, 99.5, 100.1]
    for _ in range(3):
        for p in seg:
            lo = p - 0.05 if p > 99.6 else p
            rows.append([ts, p, p + 0.1, lo, p, 1000]); ts += 1
    rows.append([ts, 99.7, 99.75, 99.45, 99.6, 2500])
    st = best_retest(rows)
    assert isinstance(st, RetestScore) and st.ok is True
    assert st.long_ok is True and st.short_ok is False
    assert abs(st.level - 99.5) < 0.2


def test_best_retest_no_level_in_band():
    st = best_retest(_baseline(n=40, px=100.0))
    assert st.ok is False or st.entry_ok is False
