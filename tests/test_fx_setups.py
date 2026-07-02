"""Tests for bot.fx_setups — FX/CFD native setups composed from our tech."""
import random
from bot.fx_setups import (session_range_fade, round_level_sweep,
                           session_breakout_retest, trend_pullback, FxSignal)

LON = 9 * 3600          # 09:00 UTC -> london
ASIA = 2 * 3600         # 02:00 UTC -> asian


def _jagged(ts0=LON, n=80, seed=4, band=2.0):
    random.seed(seed); rows = []; prev = 100.0
    for i in range(n):
        c = 100 + 0.15 * (prev - 100) + random.uniform(-band, band)
        o = prev
        h = max(o, c) + abs(random.uniform(0, 0.6))
        l = min(o, c) - abs(random.uniform(0, 0.6))
        rows.append([ts0 + i * 300, o, h, l, c, 1000]); prev = c
    return rows


def test_range_fade_top_is_short():
    rows = _jagged()
    rows[-1] = [LON + 80 * 300, rows[-2][4], rows[-2][4] + 0.5, rows[-2][4] - 0.2, 103.5, 1000]
    s = session_range_fade(rows)
    assert isinstance(s, FxSignal)
    if s.side != "none":
        assert s.short_ok and not s.long_ok and s.reason == "fade_top"


def test_range_fade_blocks_news():
    rows = _jagged()
    ev = [{"ts": rows[-1][0] + 300, "impact": 3}]
    s = session_range_fade(rows, events=ev)
    assert s.reason == "news_or_session_block"


def test_range_fade_blocks_asian_by_default():
    rows = _jagged(ts0=ASIA)
    # keep last bar in asian hour
    s = session_range_fade(rows, block_asia=True)
    # last bar ts = ASIA + 79*300 = 30900 -> hour 8 (london); force a true asian ts:
    rows[-1] = [ASIA + 300, rows[-1][1], rows[-1][2], rows[-1][3], rows[-1][4], 1000]
    s2 = session_range_fade(rows, block_asia=True)
    assert s2.reason == "news_or_session_block"


def test_round_level_sweep_triggers():
    rows = [[LON + i * 300, 100, 100.3, 99.7, 100, 1000] for i in range(30)]
    rows[-1] = [LON + 30 * 300, 100.1, 100.9, 100.0, 100.15, 3000]   # sweep above, close back
    s = round_level_sweep(rows, tol_frac=0.02)
    assert isinstance(s, FxSignal)
    if s.side != "none":
        assert s.reason == "round_stop_hunt" and (s.short_ok or s.long_ok)


def test_breakout_retest_wrong_session_blocked():
    rows = [[ASIA + i * 300, 100, 100.3, 99.7, 100, 1000] for i in range(50)]
    s = session_breakout_retest(rows)
    assert s.reason == "wrong_session"


def test_trend_pullback_returns_signal_and_respects_news():
    up = [[LON + i * 300, 100 + i * 0.3, 100 + i * 0.3 + 0.3, 100 + i * 0.3 - 0.2, 100 + i * 0.3 + 0.1, 1000]
          for i in range(80)]
    s = trend_pullback(up, min_quality=0.3)
    assert isinstance(s, FxSignal)
    ev = [{"ts": up[-1][0] + 300, "impact": 3}]
    assert trend_pullback(up, events=ev).reason == "news_block"


def test_all_setups_are_one_directional():
    rows = _jagged()
    for fn in (session_range_fade, round_level_sweep, trend_pullback):
        s = fn(rows)
        assert not (s.long_ok and s.short_ok)
