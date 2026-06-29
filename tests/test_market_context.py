import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import market_context as mc


def _row(ts, o, h, l, c, v=100.0):
    return [ts, o, h, l, c, v]


def test_pivot_highs_and_lows():
    # bar 3 is a clear swing high (peak), bar 6 a clear swing low (trough)
    rows = [
        _row(1, 10, 11, 9, 10),
        _row(2, 10, 12, 10, 11),
        _row(3, 11, 15, 11, 14),   # peak at idx 3 (high 15)
        _row(4, 14, 13, 11, 12),
        _row(5, 12, 12, 8, 9),
        _row(6, 9, 9, 5, 6),       # trough at idx 6 (low 5)
        _row(7, 6, 10, 6, 9),
        _row(8, 9, 11, 8, 10),
    ]
    ph = mc.pivot_highs(rows, 2, 2)
    pl = mc.pivot_lows(rows, 2, 2)
    assert any(p["idx"] == 2 and p["price"] == 15 for p in ph)
    assert any(p["idx"] == 5 and p["price"] == 5 for p in pl)


def test_cluster_merges_close_pivots():
    pivots = [
        {"price": 100.0, "idx": 1, "ts": 1},
        {"price": 100.4, "idx": 5, "ts": 5},
        {"price": 100.2, "idx": 9, "ts": 9},
        {"price": 120.0, "idx": 12, "ts": 12},
    ]
    clusters = mc.cluster_levels(pivots, tol=1.0)
    # three near-100 merge into one (3 touches), 120 separate
    near100 = [c for c in clusters if abs(c["level"] - 100) < 2]
    assert len(near100) == 1
    assert near100[0]["touches"] == 3
    assert near100[0]["last_idx"] == 9


def test_fit_line_perfect_slope_and_r2():
    pts = [(0.0, 0.0), (1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]  # y = 2x
    m, b, r2 = mc.fit_line(pts)
    assert abs(m - 2.0) < 1e-9
    assert abs(b - 0.0) < 1e-9
    assert abs(r2 - 1.0) < 1e-9


def test_fit_line_two_points():
    m, b, r2 = mc.fit_line([(0.0, 1.0), (2.0, 5.0)])
    assert abs(m - 2.0) < 1e-9 and abs(b - 1.0) < 1e-9 and r2 == 1.0


def test_atr_positive():
    rows = [_row(i, 10, 12, 8, 11) for i in range(20)]
    a = mc.atr(rows, 14)
    assert a > 0 and math.isfinite(a)


def test_sloped_resistance_descending():
    # descending highs -> negative slope resistance line
    rows = []
    highs = [20, 22, 19, 21, 18, 20, 17, 19, 16, 18, 15, 17]
    for i, h in enumerate(highs):
        rows.append(_row(i, h - 2, h, h - 4, h - 1))
    sl = mc.sloped_level(rows, side="resistance", left=1, right=1, min_pivots=2)
    assert sl is not None
    assert sl["slope"] < 0  # descending resistance


def test_build_context_finds_nearest_levels():
    # construct repeated resistance near 130 and support near 90, price ~110
    rows = []
    pattern = [
        (100, 105, 98, 102),
        (102, 130, 101, 112),   # tag 130
        (112, 118, 92, 95),
        (95, 119, 90, 110),     # tag 90
        (110, 131, 108, 114),   # tag ~130 again
        (114, 116, 91, 100),    # tag ~90 again
        (100, 120, 99, 110),
        (110, 121, 100, 111),
    ]
    for i, (o, h, l, c) in enumerate(pattern):
        rows.append(_row(i, o, h, l, c, 100))
    ctx = mc.build_context(rows, atr_value=10.0, pivot_left=1, pivot_right=1, min_touches=2)
    assert ctx["price"] == 111
    assert ctx["resistance"] is not None
    assert ctx["resistance"]["level"] > 111  # overhead
    assert ctx["resistance"]["touches"] >= 2
    assert ctx["support"] is not None
    assert ctx["support"]["level"] < 111
    assert ctx["resistance"]["dist_atr"] >= 0


def test_build_context_empty_and_degenerate():
    assert mc.build_context([])["price"] != mc.build_context([])["price"]  # nan
    flat = [_row(i, 10, 10, 10, 10, 0) for i in range(5)]
    ctx = mc.build_context(flat, atr_value=0.0)  # atr invalid -> safe
    assert ctx["resistance"] is None


def test_vwap_and_hvn():
    rows = [_row(i, 10, 12, 8, 10, 50 + i) for i in range(30)]
    assert math.isfinite(mc.vwap(rows))
    hvns = mc.volume_hvns(rows, bins=10, top_n=3)
    assert len(hvns) <= 3


def _trend_rows(n, start, step, amp=3, vol=100):
    # zig-zag around a sloped centerline so pivots exist on both sides
    rows = []
    for i in range(n):
        mid = start + step * i
        h = mid + amp + (1 if i % 2 else 0)
        l = mid - amp - (1 if i % 2 == 0 else 0)
        o = mid - 0.5
        c = mid + 0.5
        rows.append([i, o, h, l, c, vol])
    return rows


def test_classify_channel_flat():
    rows = _trend_rows(60, 100, 0.0)  # no drift
    r = mc.classify_channel(rows, atr_value=4.0, pivot_left=1, pivot_right=1)
    assert r["regime"] == "flat"
    assert abs(r["slope_atr"]) <= 0.04 + 1e-9


def test_classify_channel_ascending():
    rows = _trend_rows(60, 100, 1.0)  # +1/bar
    r = mc.classify_channel(rows, atr_value=4.0, pivot_left=1, pivot_right=1)
    assert r["regime"] == "ascending"
    assert r["slope_atr"] > 0


def test_classify_channel_descending():
    rows = _trend_rows(60, 200, -1.0)  # -1/bar
    r = mc.classify_channel(rows, atr_value=4.0, pivot_left=1, pivot_right=1)
    assert r["regime"] == "descending"
    assert r["slope_atr"] < 0


def test_classify_channel_position_and_width():
    rows = _trend_rows(60, 100, 0.0, amp=5)
    r = mc.classify_channel(rows, atr_value=4.0, pivot_left=1, pivot_right=1)
    # price (~mid+0.5) should sit roughly mid-channel
    if r["pos_in_channel"] == r["pos_in_channel"]:
        assert 0.0 <= r["pos_in_channel"] <= 1.0
    assert r["width_atr"] >= 0


def test_classify_channel_empty_safe():
    r = mc.classify_channel([])
    assert r["regime"] == "unknown"
