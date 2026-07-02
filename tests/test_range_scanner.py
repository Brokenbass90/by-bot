"""Tests for bot.range_scanner — pick the right ranging instruments for a grid."""
import random
from bot.range_scanner import scan, best_ranging, score_instrument, RangeScore


def _range(seed, band=3.0, n=140):
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


def _uni():
    return {"RANGE_A": _range(3), "RANGE_B": _range(7, band=2.5),
            "TREND_C": _trend(), "CHAOS_D": _range(9, band=8.0)}


def test_insufficient_data():
    s = score_instrument("X", [[i, 1, 1, 1, 1, 1] for i in range(10)])
    assert isinstance(s, RangeScore) and s.tradeable is False


def test_trend_scores_low():
    s = score_instrument("TREND", _trend())
    assert s.tradeable is False and s.score < 0.5


def test_range_scores_higher_than_trend():
    r = score_instrument("R", _range(7, band=2.5))
    t = score_instrument("T", _trend())
    assert r.score > t.score


def test_scan_is_ranked_and_tradeable_first():
    ranked = scan(_uni())
    assert ranked[0].tradeable is True or all(not x.tradeable for x in ranked)
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True) or ranked[0].tradeable


def test_best_ranging_excludes_trend_and_chaos():
    best = best_ranging(_uni(), top_n=5)
    assert "TREND_C" not in best and "CHAOS_D" not in best


def test_chaos_high_vol_not_tradeable():
    s = score_instrument("CHAOS", _range(9, band=10.0))
    assert s.tradeable is False
